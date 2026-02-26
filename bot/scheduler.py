import anthropic
from datetime import time, timezone, timedelta
from telegram import Bot
from bot.memory.database import get_all_users, get_active_users, get_user, add_message
from bot.memory.context_builder import build_context
from shared.config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL_FAST,
    MORNING_CHECKIN_HOUR, MORNING_CHECKIN_MINUTE,
    EVENING_CHECKIN_HOUR, EVENING_CHECKIN_MINUTE,
)

MOSCOW_TZ = timezone(timedelta(hours=3))

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

MORNING_SYSTEM = """Ты — AI-наставник. Сейчас утро. Твоя задача — короткий утренний чек-ин.
Напомни пользователю о его цели и спроси: что конкретно он сделает сегодня для её достижения?
Максимум 2-3 предложения. Один вопрос в конце. Без воды."""

EVENING_SYSTEM = """Ты — AI-наставник. Сейчас вечер. Твоя задача — вечерний чек-ин.
Спроси пользователя: выполнил ли он то, что планировал утром?
Если нет — не жалей, спроси почему и что изменит завтра.
Максимум 2-3 предложения. Один вопрос в конце."""

WEEKLY_SYSTEM = """Ты — AI-наставник. Сейчас конец недели. Проведи короткий еженедельный разбор.
На основе профиля пользователя:
1. Отметь прогресс (если есть)
2. Назови главный паттерн недели
3. Задай один главный вопрос на следующую неделю
Максимум 4-5 предложений."""


async def _send_checkin(bot: Bot, telegram_id: int, system: str, checkin_type: str):
    user = await get_user(telegram_id)
    if not user or user["phase"] == "onboarding":
        return
    _, messages = await build_context(user)
    try:
        response = await client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=200,
            system=system + f"\n\nПрофиль: {user.get('name')}, цель: {user.get('goal', 'не поставлена')}",
            messages=messages[-6:] if messages else [{"role": "user", "content": "начни чек-ин"}],
        )
        text = response.content[0].text
        await bot.send_message(chat_id=telegram_id, text=text)
        await add_message(telegram_id, "assistant", f"[{checkin_type}] {text}")
    except Exception as e:
        print(f"Checkin error for {telegram_id}: {e}")


async def morning_checkin(context):
    bot: Bot = context.bot
    users = await get_active_users(days=7)
    for user in users:
        await _send_checkin(bot, user["telegram_id"], MORNING_SYSTEM, "morning_checkin")


async def evening_checkin(context):
    bot: Bot = context.bot
    users = await get_active_users(days=7)
    for user in users:
        await _send_checkin(bot, user["telegram_id"], EVENING_SYSTEM, "evening_checkin")


async def weekly_review(context):
    bot: Bot = context.bot
    users = await get_active_users(days=7)
    for user in users:
        await _send_checkin(bot, user["telegram_id"], WEEKLY_SYSTEM, "weekly_review")


def setup_scheduler(app):
    job_queue = app.job_queue
    moscow_tz = timezone(timedelta(hours=3))

    job_queue.run_daily(
        morning_checkin,
        time=time(
            hour=MORNING_CHECKIN_HOUR,
            minute=MORNING_CHECKIN_MINUTE,
            tzinfo=moscow_tz,
        ),
        name="morning_checkin",
    )
    job_queue.run_daily(
        evening_checkin,
        time=time(
            hour=EVENING_CHECKIN_HOUR,
            minute=EVENING_CHECKIN_MINUTE,
            tzinfo=moscow_tz,
        ),
        name="evening_checkin",
    )
    job_queue.run_daily(
        weekly_review,
        time=time(hour=12, minute=0, tzinfo=moscow_tz),
        days=(6,),
        name="weekly_review",
    )
