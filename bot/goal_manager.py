"""Менеджер целей: CRUD + генерация шагов через LLM.

Модуль не знает о Telegram — только работа с БД и LLM.
7 публичных функций: create_goal, generate_steps, complete_step,
skip_step, get_today_steps, get_overdue_steps, archive_goal.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from shared.llm_client import LLMError, call_gpt
from shared.models import Goal, GoalStep
from bot.memory.database import (
    add_goal_step,
    create_goal as db_create_goal,
    get_active_goal,
    get_db,
    get_overdue_steps as db_get_overdue_steps,
    get_steps_by_deadline,
    update_goal_status,
    update_step_status,
    _now,
)
from bot.prompts.memory_prompts import GOAL_STEPS_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Приватные хелперы
# ---------------------------------------------------------------------------


async def _get_goal_by_id(goal_id: int) -> dict | None:
    """Получить цель по id."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM goals WHERE id = ?", (goal_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def _get_step_by_id(step_id: int) -> dict | None:
    """Получить шаг по id."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM goal_steps WHERE id = ?", (step_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


def _row_to_goal_step(row: dict) -> GoalStep:
    """Конвертировать dict-строку из БД в GoalStep."""
    return GoalStep(
        id=row["id"],
        goal_id=row["goal_id"],
        telegram_id=row["telegram_id"],
        title=row["title"],
        status=row["status"],
        sort_order=row["sort_order"],
        deadline_at=row.get("deadline_at"),
        completed_at=row.get("completed_at"),
    )


# ---------------------------------------------------------------------------
# Публичные функции
# ---------------------------------------------------------------------------


async def create_goal(telegram_id: int, title: str) -> Goal:
    """Создать цель. Только одна активная цель на пользователя."""
    existing = await get_active_goal(telegram_id)
    if existing is not None:
        raise ValueError("User already has an active goal")

    goal_id = await db_create_goal(telegram_id, title)
    logger.info("create_goal: user=%s goal_id=%s title=%r", telegram_id, goal_id, title)
    return Goal(id=goal_id, telegram_id=telegram_id, title=title, status="active")


async def generate_steps(goal_id: int, context: str) -> list[GoalStep]:
    """Сгенерировать 3-7 шагов для цели через LLM."""
    goal = await _get_goal_by_id(goal_id)
    if goal is None:
        logger.warning("generate_steps: goal_id=%s not found", goal_id)
        return []

    prompt = GOAL_STEPS_PROMPT.format(goal_title=goal["title"], context=context)

    try:
        response = await call_gpt(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        data = json.loads(response)
        steps_raw = data["steps"][:7]
    except (json.JSONDecodeError, LLMError, TypeError, KeyError) as exc:
        logger.warning("generate_steps: goal_id=%s error=%s", goal_id, exc)
        return []

    result: list[GoalStep] = []
    for i, step in enumerate(steps_raw):
        try:
            deadline_at = (
                datetime.now(timezone.utc) + timedelta(days=step["deadline_days"])
            ).strftime("%Y-%m-%d %H:%M:%S")

            step_id = await add_goal_step(
                goal_id=goal_id,
                telegram_id=goal["telegram_id"],
                title=step["title"],
                sort_order=i,
                deadline_at=deadline_at,
            )
            result.append(
                GoalStep(
                    id=step_id,
                    goal_id=goal_id,
                    telegram_id=goal["telegram_id"],
                    title=step["title"],
                    status="pending",
                    sort_order=i,
                    deadline_at=deadline_at,
                )
            )
        except (TypeError, KeyError) as exc:
            logger.warning(
                "generate_steps: goal_id=%s step_index=%d error=%s", goal_id, i, exc
            )
            continue

    logger.info("generate_steps: goal_id=%s steps_created=%d", goal_id, len(result))
    return result


async def complete_step(step_id: int) -> GoalStep:
    """Отметить шаг как выполненный."""
    step = await _get_step_by_id(step_id)
    if step is None:
        raise ValueError("Step not found")

    now = _now()
    await update_step_status(step_id, status="done", completed_at=now)

    return GoalStep(
        id=step["id"],
        goal_id=step["goal_id"],
        telegram_id=step["telegram_id"],
        title=step["title"],
        status="done",
        sort_order=step["sort_order"],
        deadline_at=step.get("deadline_at"),
        completed_at=now,
    )


async def skip_step(step_id: int) -> GoalStep:
    """Пропустить шаг."""
    step = await _get_step_by_id(step_id)
    if step is None:
        raise ValueError("Step not found")

    now = _now()
    await update_step_status(step_id, status="skipped", completed_at=now)

    return GoalStep(
        id=step["id"],
        goal_id=step["goal_id"],
        telegram_id=step["telegram_id"],
        title=step["title"],
        status="skipped",
        sort_order=step["sort_order"],
        deadline_at=step.get("deadline_at"),
        completed_at=now,
    )


async def get_today_steps(telegram_id: int) -> list[GoalStep]:
    """Получить шаги с дедлайном на сегодня."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = await get_steps_by_deadline(telegram_id, today)
    return [_row_to_goal_step(row) for row in rows]


async def get_overdue_steps(telegram_id: int) -> list[GoalStep]:
    """Получить просроченные шаги."""
    rows = await db_get_overdue_steps(telegram_id)
    return [_row_to_goal_step(row) for row in rows]


async def archive_goal(goal_id: int) -> Goal:
    """Архивировать цель."""
    goal = await _get_goal_by_id(goal_id)
    if goal is None:
        raise ValueError("Goal not found")

    now = _now()
    await update_goal_status(goal_id, status="archived", archived_at=now)

    return Goal(
        id=goal["id"],
        telegram_id=goal["telegram_id"],
        title=goal["title"],
        status="archived",
        created_at=goal.get("created_at"),
        archived_at=now,
    )
