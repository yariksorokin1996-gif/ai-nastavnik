"""Сбор обратной связи через inline-кнопки Telegram.

Scheduler job: каждые 30 мин проверяет эпизоды,
отправляет ask_feeling (через 2ч) и ask_enactment (через 12ч).
Тихие часы 23:00-09:00 MSK.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from bot.memory import database
from bot.memory.database import get_db

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3))

# Тайминги
FEELING_DELAY_HOURS = 2
FEELING_COOLDOWN_HOURS = 8
ENACTMENT_DELAY_HOURS = 12
QUIET_HOUR_START = 23  # MSK
QUIET_HOUR_END = 9     # MSK


def _is_quiet_hours() -> bool:
    """Тихие часы 23:00-09:00 MSK."""
    hour = datetime.now(MOSCOW_TZ).hour
    return hour >= QUIET_HOUR_START or hour < QUIET_HOUR_END


async def check_pending_feedback(context) -> None:
    """APScheduler job: каждые 30 мин. Проверяет эпизоды и отправляет feedback."""
    if _is_quiet_hours():
        return

    bot: Bot = context.bot

    # Найти все эпизоды, подходящие для ask_feeling
    # Условие: created_at <= NOW - 2ч, нет feedback с feeling_after IS NOT NULL,
    # нет отправленных (sent=1) feedback для этого эпизода
    async with get_db() as db:
        async with db.execute(
            """SELECT e.id, e.telegram_id, e.session_end, e.messages_count
               FROM episodes e
               WHERE e.created_at <= datetime('now', '-2 hours')
                 AND NOT EXISTS (
                   SELECT 1 FROM session_feedback sf
                   WHERE sf.episode_id = e.id AND sf.feeling_after IS NOT NULL
                 )
                 AND NOT EXISTS (
                   SELECT 1 FROM session_feedback sf
                   WHERE sf.episode_id = e.id AND sf.sent = 1
                 )
               ORDER BY e.created_at DESC"""
        ) as cur:
            episodes_for_feeling = [dict(r) for r in await cur.fetchall()]

    for ep in episodes_for_feeling:
        try:
            await ask_feeling(ep["telegram_id"], ep["id"], bot)
        except Exception:
            logger.error("ask_feeling failed for episode %s", ep["id"], exc_info=True)

    # Найти всех пользователей с commitments для ask_enactment
    async with get_db() as db:
        async with db.execute(
            """SELECT DISTINCT e.telegram_id
               FROM episodes e
               WHERE e.commitments_json IS NOT NULL AND e.commitments_json != '[]'
                 AND e.created_at <= datetime('now', '-12 hours')
                 AND NOT EXISTS (
                   SELECT 1 FROM session_feedback sf
                   WHERE sf.episode_id = e.id AND sf.tried_in_practice IS NOT NULL
                 )"""
        ) as cur:
            users_for_enactment = [dict(r) for r in await cur.fetchall()]

    for row in users_for_enactment:
        try:
            await ask_enactment(row["telegram_id"], bot)
        except Exception:
            logger.error(
                "ask_enactment failed for user %s", row["telegram_id"], exc_info=True
            )


async def ask_feeling(telegram_id: int, episode_id: int, bot: Bot) -> bool:
    """Отправляет inline-кнопки 'Стало ли лучше после разговора?'

    Возвращает True если отправлено.
    """
    if _is_quiet_hours():
        return False

    async with get_db() as db:
        # Условие 1: episode существует
        async with db.execute(
            "SELECT created_at, session_end, messages_count FROM episodes WHERE id = ?",
            (episode_id,),
        ) as cur:
            episode = await cur.fetchone()
        if not episode:
            return False

        ep = dict(episode)

        # Условие 4: >= 3 сообщений
        if (ep.get("messages_count") or 0) < 3:
            return False

        # Условие 2: нет feedback с feeling_after
        async with db.execute(
            "SELECT 1 FROM session_feedback WHERE episode_id = ? AND feeling_after IS NOT NULL",
            (episode_id,),
        ) as cur:
            if await cur.fetchone():
                return False

        # Проверяем нет ли уже отправленного (sent=1) для этого эпизода
        async with db.execute(
            "SELECT 1 FROM session_feedback WHERE episode_id = ? AND sent = 1",
            (episode_id,),
        ) as cur:
            if await cur.fetchone():
                return False

        # Условие 3: юзер НЕ писал после session_end
        session_end = ep.get("session_end")
        if session_end:
            async with db.execute(
                "SELECT 1 FROM messages WHERE telegram_id = ? AND role = 'user' AND created_at > ?",
                (telegram_id, session_end),
            ) as cur:
                if await cur.fetchone():
                    return False

        # Условие 5: cooldown 8ч
        async with db.execute(
            """SELECT MAX(created_at) as last_sent FROM session_feedback
               WHERE telegram_id = ? AND sent = 1""",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
        if row and row["last_sent"]:
            last = datetime.fromisoformat(row["last_sent"])
            if (
                datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)
                < timedelta(hours=FEELING_COOLDOWN_HOURS)
            ):
                return False

    # Всё ОК — создаём feedback запись и отправляем кнопки
    feedback_id = await database.create_feedback(
        telegram_id=telegram_id,
        episode_id=episode_id,
        session_end=ep.get("session_end", ""),
        messages_in_session=ep.get("messages_count", 0),
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Лучше \U0001f49b", callback_data=f"feeling:{feedback_id}:1"),
            InlineKeyboardButton("Так же", callback_data=f"feeling:{feedback_id}:2"),
            InlineKeyboardButton("Хуже", callback_data=f"feeling:{feedback_id}:3"),
        ]
    ])

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text="Стало ли тебе лучше после нашего разговора?",
            reply_markup=keyboard,
        )
        await database.mark_feedback_sent(feedback_id)
        return True
    except Exception:
        logger.warning("Failed to send feeling buttons to %s", telegram_id, exc_info=True)
        return False


async def ask_enactment(telegram_id: int, bot: Bot) -> bool:
    """Отправляет inline-кнопки 'Получилось попробовать?'

    Возвращает True если отправлено.
    """
    if _is_quiet_hours():
        return False

    async with get_db() as db:
        # Условие 3: cooldown 1 раз в день
        async with db.execute(
            """SELECT 1 FROM session_feedback
               WHERE telegram_id = ? AND tried_in_practice IS NOT NULL
                 AND DATE(created_at) = DATE('now')""",
            (telegram_id,),
        ) as cur:
            if await cur.fetchone():
                return False

        # Условие 1: episode с commitments >= 12ч
        async with db.execute(
            """SELECT id, commitments_json FROM episodes
               WHERE telegram_id = ?
                 AND commitments_json IS NOT NULL AND commitments_json != '[]'
                 AND created_at <= datetime('now', '-12 hours')
               ORDER BY created_at DESC LIMIT 1""",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False

        ep = dict(row)
        episode_id = ep["id"]

        # Условие 2: нет tried_in_practice для этого эпизода
        async with db.execute(
            "SELECT 1 FROM session_feedback WHERE episode_id = ? AND tried_in_practice IS NOT NULL",
            (episode_id,),
        ) as cur:
            if await cur.fetchone():
                return False

    # Парсим commitment
    try:
        commitments = json.loads(ep["commitments_json"])
        if not commitments:
            return False
        commitment = commitments[0]
    except (json.JSONDecodeError, IndexError):
        return False

    # Создаём feedback и отправляем
    feedback_id = await database.create_feedback(
        telegram_id=telegram_id,
        episode_id=episode_id,
        session_end="",
        messages_in_session=0,
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да! \U0001f389", callback_data=f"enact:{feedback_id}:1"),
            InlineKeyboardButton("Пока нет", callback_data=f"enact:{feedback_id}:0"),
        ]
    ])

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"\u0422\u044b \u0433\u043e\u0432\u043e\u0440\u0438\u043b\u0430: \u00ab{commitment}\u00bb. \u041f\u043e\u043b\u0443\u0447\u0438\u043b\u043e\u0441\u044c \u043f\u043e\u043f\u0440\u043e\u0431\u043e\u0432\u0430\u0442\u044c?",
            reply_markup=keyboard,
        )
        await database.mark_feedback_sent(feedback_id)
        return True
    except Exception:
        logger.warning("Failed to send enactment buttons to %s", telegram_id, exc_info=True)
        return False
