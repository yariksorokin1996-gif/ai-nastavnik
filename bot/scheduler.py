"""Планировщик фоновых задач (python-telegram-bot job_queue).

Задачи:
    1. send_daily_messages — ежедневно 19:00 MSK
    2. check_silence — каждые 6 часов
    3. run_full_memory_update — каждые 5 минут
    4. check_pending_feedback — каждые 30 минут
    5. generate_daily_report — ежедневно 09:00 MSK
    6. generate_weekly_report — воскресенье 12:00 MSK
"""
from __future__ import annotations

import logging
from datetime import time, timedelta, timezone

from bot.analytics.daily_report import generate_daily_report
from bot.analytics.feedback_collector import check_pending_feedback
from bot.analytics.weekly_report import generate_weekly_report
from bot.daily_messenger import send_daily_messages, check_silence
from bot.memory.full_memory_update import run_full_memory_update

logger = logging.getLogger(__name__)

MOSCOW_TZ = timezone(timedelta(hours=3))


async def _full_memory_update_job(context) -> None:
    """Обёртка для run_full_memory_update (не принимает context)."""
    await run_full_memory_update()


def setup_scheduler(app) -> None:
    """Регистрирует все фоновые задачи в job_queue приложения."""
    job_queue = app.job_queue

    # 1. Ежедневные сообщения — 19:00 MSK
    job_queue.run_daily(
        send_daily_messages,
        time=time(hour=19, minute=0, tzinfo=MOSCOW_TZ),
        name="send_daily_messages",
    )

    # 2. Проверка тишины — каждые 6 часов
    job_queue.run_repeating(
        check_silence,
        interval=timedelta(hours=6),
        first=timedelta(minutes=10),
        name="check_silence",
    )

    # 3. Полное обновление памяти — каждые 5 минут
    job_queue.run_repeating(
        _full_memory_update_job,
        interval=timedelta(minutes=5),
        first=timedelta(minutes=2),
        name="full_memory_update",
    )

    # 4. Проверка pending feedback — каждые 30 минут
    job_queue.run_repeating(
        check_pending_feedback,
        interval=timedelta(minutes=30),
        first=timedelta(minutes=5),
        name="check_pending_feedback",
    )

    # 5. Ежедневный отчёт — 09:00 MSK
    job_queue.run_daily(
        generate_daily_report,
        time=time(hour=9, minute=0, tzinfo=MOSCOW_TZ),
        name="daily_report",
    )

    # 6. Еженедельная сводка — воскресенье 12:00 MSK
    job_queue.run_daily(
        generate_weekly_report,
        time=time(hour=12, minute=0, tzinfo=MOSCOW_TZ),
        days=(6,),
        name="weekly_report",
    )

    logger.info(
        "Scheduler: 6 jobs registered "
        "(daily_messages, silence_check, memory_update, "
        "feedback_collector, daily_report, weekly_report)"
    )
