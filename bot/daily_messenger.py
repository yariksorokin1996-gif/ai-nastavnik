"""
Ежедневные сообщения и напоминания о тишине (APScheduler jobs).

Контракт:
    generate_daily_message(telegram_id, day_number) -> str
        Вход: telegram_id (int), day_number (int)
        Выход: текст сообщения (str, <=500 символов)
        Ошибки: LLMError -> random.choice(FALLBACK_DAILY_MESSAGES)

    send_daily_messages(context) -> None
        APScheduler job, daily 19:00 MSK
        Первые 7 дней: шлёт каждый день
        После 7 дней: только если тишина > 48h
        СТОП: 3 дня без ответа -> пропуск
        Защита: cooldown 2h, idempotency (1 msg/day)

    check_silence(context) -> None
        APScheduler job, every 6h
        Триггер: last_message_at > 24h назад
        Защита: cooldown 6h, СТОП при 3 днях молчания
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from shared.llm_client import LLMError, call_gpt
from bot.memory import database
from bot.memory import profile_manager
from bot.prompts.memory_prompts import DAILY_MESSAGE_PROMPT, FALLBACK_DAILY_MESSAGES

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3))

# Защитные интервалы
_DAILY_COOLDOWN_HOURS = 2
_SILENCE_COOLDOWN_HOURS = 6

# Лимиты
_FIRST_WEEK_DAYS = 7
_SILENCE_THRESHOLD_HOURS = 48
_STOP_DAYS = 3
_SILENCE_TRIGGER_HOURS = 24
_MAX_MESSAGE_CHARS = 500


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _now() -> str:
    """UTC datetime строкой, совместимо с SQLite."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now_utc() -> datetime:
    """UTC datetime объект."""
    return datetime.now(timezone.utc)


def _parse_dt(dt_str: str | None) -> datetime | None:
    """Парсит строку datetime из SQLite. None если пусто."""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None


def _get_day_number(user: dict) -> int:
    """Вычисляет номер дня общения из created_at пользователя."""
    created = _parse_dt(user.get("created_at"))
    if created is None:
        return 1
    delta = _now_utc() - created
    return max(1, delta.days + 1)


def _get_time_of_day() -> str:
    """Время суток по Москве."""
    msk_now = datetime.now(MOSCOW_TZ)
    hour = msk_now.hour
    if 6 <= hour < 12:
        return "утро"
    elif 12 <= hour < 17:
        return "день"
    elif 17 <= hour < 23:
        return "вечер"
    return "ночь"


async def _get_sensitive_topics(telegram_id: int) -> str:
    """Извлекает чувствительные темы из профиля."""
    profile = await profile_manager.get_profile(telegram_id)
    if profile is None or not profile.sensitive_topics:
        return "Нет чувствительных тем"
    return ", ".join(profile.sensitive_topics)


def _hours_since(dt_str: str | None) -> float:
    """Сколько часов прошло от dt_str до сейчас. Inf если None."""
    dt = _parse_dt(dt_str)
    if dt is None:
        return float("inf")
    delta = _now_utc() - dt
    return delta.total_seconds() / 3600


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


async def generate_daily_message(telegram_id: int, day_number: int) -> str:
    """Генерирует персонализированное ежедневное сообщение.

    Контракт:
        Вход: telegram_id (int), day_number (int, >= 1)
        Выход: текст сообщения (str, <=500 символов)
        Ошибки: LLMError -> random.choice(FALLBACK_DAILY_MESSAGES)
    """
    try:
        profile_text = await profile_manager.get_profile_as_text(telegram_id)
        if not profile_text:
            profile_text = "Профиль не заполнен"

        sensitive_topics = await _get_sensitive_topics(telegram_id)
        time_of_day = _get_time_of_day()

        prompt = DAILY_MESSAGE_PROMPT.format(
            profile_text=profile_text,
            day_number=day_number,
            time_of_day=time_of_day,
            sensitive_topics=sensitive_topics,
        )

        text = await call_gpt(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            timeout=15,
        )

        if len(text) > _MAX_MESSAGE_CHARS:
            trimmed = text[:_MAX_MESSAGE_CHARS].rsplit(" ", 1)[0]
            # Если обрезка по пробелу дала слишком короткий текст — режем жёстко
            text = trimmed if len(trimmed) > _MAX_MESSAGE_CHARS // 2 else text[:_MAX_MESSAGE_CHARS]

        return text

    except (LLMError, ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "generate_daily_message failed for user %s: %s", telegram_id, exc
        )
        return random.choice(FALLBACK_DAILY_MESSAGES)


async def send_daily_messages(context) -> None:
    """APScheduler job: ежедневная рассылка 19:00 MSK.

    Guards:
        0. message_count == 0 -> пропуск
        1. уже отправлено сегодня -> пропуск (idempotency)
        2. cooldown 2ч (last_automated_msg_at)
        3. 3 дня без ответа -> пропуск (СТОП)
        4. после 7 дней: только если тишина > 48ч
    """
    bot = context.bot
    users = await database.get_all_users()

    for user in users:
        tid = user["telegram_id"]
        try:
            # Guard 0: не писал ни разу
            if user.get("messages_total", 0) == 0:
                continue

            # Guard 1: idempotency — уже отправлено сегодня
            if await database.has_daily_today(tid):
                continue

            # Guard 2: cooldown 2 часа
            if _hours_since(user.get("last_automated_msg_at")) < _DAILY_COOLDOWN_HOURS:
                continue

            # Guard 3: 3 дня без ответа -> прекращаем
            hours_silent = _hours_since(user.get("last_message_at"))
            if hours_silent >= _STOP_DAYS * 24:
                continue

            day_number = _get_day_number(user)

            # Guard 4: после первой недели — только если тишина > 48ч
            if day_number > _FIRST_WEEK_DAYS:
                if hours_silent < _SILENCE_THRESHOLD_HOURS:
                    continue

            # Генерируем и отправляем
            text = await generate_daily_message(tid, day_number)
            await bot.send_message(chat_id=tid, text=text)

            # Записываем в БД
            await database.create_daily_message(
                tid, text, day_number, source="daily_message"
            )
            await database.add_message(tid, "assistant", text, source="daily_message")
            await database.update_user(tid, last_automated_msg_at=_now())

            logger.info("Daily message sent to user %s (day %d)", tid, day_number)

        except (LLMError, ValueError, TypeError, KeyError) as exc:
            logger.error("send_daily_messages error for user %s: %s", tid, exc)
        except Exception as exc:
            logger.error(
                "send_daily_messages telegram error for user %s: %s", tid, exc
            )


async def check_silence(context) -> None:
    """APScheduler job: каждые 6 часов проверяет молчание.

    Guards:
        0. message_count == 0 -> пропуск
        1. cooldown 6ч (last_automated_msg_at)
        2. молчание > 24ч (триггер)
        3. 3 дня без ответа -> пропуск (СТОП)
    """
    bot = context.bot
    users = await database.get_all_users()

    for user in users:
        tid = user["telegram_id"]
        try:
            # Guard 0: не писал ни разу
            if user.get("messages_total", 0) == 0:
                continue

            # Guard 1: cooldown 6 часов
            if _hours_since(user.get("last_automated_msg_at")) < _SILENCE_COOLDOWN_HOURS:
                continue

            # Guard 2: молчание > 24ч
            hours_silent = _hours_since(user.get("last_message_at"))
            if hours_silent < _SILENCE_TRIGGER_HOURS:
                continue

            # Guard 3: 3 дня без ответа -> прекращаем
            if hours_silent >= _STOP_DAYS * 24:
                continue

            day_number = _get_day_number(user)

            # Генерируем и отправляем
            text = await generate_daily_message(tid, day_number)
            await bot.send_message(chat_id=tid, text=text)

            # Записываем в БД
            await database.create_daily_message(
                tid, text, day_number, source="silence_reminder"
            )
            await database.add_message(
                tid, "assistant", text, source="silence_reminder"
            )
            await database.update_user(tid, last_automated_msg_at=_now())

            logger.info(
                "Silence reminder sent to user %s (silent %.1fh)",
                tid, hours_silent,
            )

        except (LLMError, ValueError, TypeError, KeyError) as exc:
            logger.error("check_silence error for user %s: %s", tid, exc)
        except Exception as exc:
            logger.error(
                "check_silence telegram error for user %s: %s", tid, exc
            )
