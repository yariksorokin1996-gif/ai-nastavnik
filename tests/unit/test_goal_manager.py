"""
Тесты для bot/goal_manager.py
12 тестов с реальной SQLite БД (tmp_path).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import pytest_asyncio

from shared.llm_client import LLMError
from shared.models import Goal, GoalStep

USER_ID = 200001


# ---------------------------------------------------------------------------
# Фикстура: подмена DB_PATH на временный файл + init_db
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def goal_db(tmp_path, monkeypatch):
    """Подменяет DB_PATH, создаёт таблицы, юзера."""
    db_file = str(tmp_path / "goal_test.db")
    monkeypatch.setattr("bot.memory.database.DB_PATH", db_file)
    monkeypatch.setattr("shared.config.DB_PATH", db_file)

    from bot.memory.database import create_user, init_db

    await init_db()
    await create_user(telegram_id=USER_ID, name="Тест")
    return db_file


# ---------------------------------------------------------------------------
# 1. test_create_goal_success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_goal_success(goal_db):
    """Создание цели: возвращает Goal с title и status='active'."""
    from bot.goal_manager import create_goal

    goal = await create_goal(USER_ID, "Поговорить с мамой")

    assert isinstance(goal, Goal)
    assert goal.title == "Поговорить с мамой"
    assert goal.status == "active"
    assert goal.telegram_id == USER_ID
    assert goal.id is not None


# ---------------------------------------------------------------------------
# 2. test_create_goal_already_active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_goal_already_active(goal_db):
    """Вторая активная цель -> ValueError."""
    from bot.goal_manager import create_goal

    await create_goal(USER_ID, "Первая цель")

    with pytest.raises(ValueError, match="already has an active goal"):
        await create_goal(USER_ID, "Вторая цель")


# ---------------------------------------------------------------------------
# 3. test_generate_steps_success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.goal_manager.call_gpt")
async def test_generate_steps_success(mock_call_gpt, goal_db):
    """generate_steps создаёт 3 шага из ответа LLM."""
    from bot.goal_manager import create_goal, generate_steps

    goal = await create_goal(USER_ID, "Поговорить с мамой")

    mock_call_gpt.return_value = json.dumps({
        "steps": [
            {"title": "Шаг 1", "deadline_days": 1},
            {"title": "Шаг 2", "deadline_days": 3},
            {"title": "Шаг 3", "deadline_days": 7},
        ]
    })

    steps = await generate_steps(goal.id, "контекст")

    assert len(steps) == 3
    for step in steps:
        assert isinstance(step, GoalStep)
        assert step.deadline_at is not None
    assert steps[0].title == "Шаг 1"
    assert steps[2].title == "Шаг 3"
    mock_call_gpt.assert_called_once()


# ---------------------------------------------------------------------------
# 4. test_generate_steps_max_7
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.goal_manager.call_gpt")
async def test_generate_steps_max_7(mock_call_gpt, goal_db):
    """LLM возвращает 10 шагов -> обрезается до 7."""
    from bot.goal_manager import create_goal, generate_steps

    goal = await create_goal(USER_ID, "Большая цель")

    ten_steps = [{"title": f"Шаг {i}", "deadline_days": i} for i in range(1, 11)]
    mock_call_gpt.return_value = json.dumps({"steps": ten_steps})

    steps = await generate_steps(goal.id, "контекст")

    assert len(steps) == 7


# ---------------------------------------------------------------------------
# 5. test_generate_steps_llm_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.goal_manager.call_gpt")
async def test_generate_steps_llm_error(mock_call_gpt, goal_db):
    """LLMError -> пустой список."""
    from bot.goal_manager import create_goal, generate_steps

    goal = await create_goal(USER_ID, "Цель")

    mock_call_gpt.side_effect = LLMError("fail")

    result = await generate_steps(goal.id, "контекст")

    assert result == []


# ---------------------------------------------------------------------------
# 6. test_complete_step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_step(goal_db):
    """complete_step -> status='done', completed_at заполнен."""
    from bot.goal_manager import complete_step, create_goal
    from bot.memory.database import add_goal_step

    goal = await create_goal(USER_ID, "Цель")
    step_id = await add_goal_step(
        goal_id=goal.id,
        telegram_id=USER_ID,
        title="Шаг тестовый",
        sort_order=0,
    )

    result = await complete_step(step_id)

    assert isinstance(result, GoalStep)
    assert result.status == "done"
    assert result.completed_at is not None


# ---------------------------------------------------------------------------
# 7. test_skip_step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_step(goal_db):
    """skip_step -> status='skipped'."""
    from bot.goal_manager import create_goal, skip_step
    from bot.memory.database import add_goal_step

    goal = await create_goal(USER_ID, "Цель")
    step_id = await add_goal_step(
        goal_id=goal.id,
        telegram_id=USER_ID,
        title="Шаг пропуск",
        sort_order=0,
    )

    result = await skip_step(step_id)

    assert isinstance(result, GoalStep)
    assert result.status == "skipped"


# ---------------------------------------------------------------------------
# 8. test_complete_step_not_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_step_not_found(goal_db):
    """complete_step для несуществующего step_id -> ValueError."""
    from bot.goal_manager import complete_step

    with pytest.raises(ValueError, match="Step not found"):
        await complete_step(9999)


# ---------------------------------------------------------------------------
# 8b. test_skip_step_not_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_step_not_found(goal_db):
    """skip_step для несуществующего step_id -> ValueError."""
    from bot.goal_manager import skip_step

    with pytest.raises(ValueError, match="Step not found"):
        await skip_step(9999)


# ---------------------------------------------------------------------------
# 9. test_get_today_steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_today_steps(goal_db):
    """Шаг с deadline на сегодня -> попадает в get_today_steps."""
    from bot.goal_manager import create_goal, get_today_steps
    from bot.memory.database import add_goal_step

    goal = await create_goal(USER_ID, "Цель")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await add_goal_step(
        goal_id=goal.id,
        telegram_id=USER_ID,
        title="Сегодняшний шаг",
        sort_order=0,
        deadline_at=today,
    )

    steps = await get_today_steps(USER_ID)

    assert len(steps) >= 1
    titles = [s.title for s in steps]
    assert "Сегодняшний шаг" in titles


# ---------------------------------------------------------------------------
# 10. test_get_overdue_steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_overdue_steps(goal_db):
    """Шаг с deadline вчера -> попадает в get_overdue_steps."""
    from bot.goal_manager import create_goal, get_overdue_steps
    from bot.memory.database import add_goal_step

    goal = await create_goal(USER_ID, "Цель")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    await add_goal_step(
        goal_id=goal.id,
        telegram_id=USER_ID,
        title="Просроченный шаг",
        sort_order=0,
        deadline_at=yesterday,
    )

    steps = await get_overdue_steps(USER_ID)

    assert len(steps) >= 1
    titles = [s.title for s in steps]
    assert "Просроченный шаг" in titles


# ---------------------------------------------------------------------------
# 11. test_archive_goal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_goal(goal_db):
    """archive_goal -> status='archived', archived_at заполнен."""
    from bot.goal_manager import archive_goal, create_goal

    goal = await create_goal(USER_ID, "Цель для архива")

    result = await archive_goal(goal.id)

    assert isinstance(result, Goal)
    assert result.status == "archived"
    assert result.archived_at is not None


# ---------------------------------------------------------------------------
# 12. test_archive_goal_not_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_goal_not_found(goal_db):
    """archive_goal для несуществующего goal_id -> ValueError."""
    from bot.goal_manager import archive_goal

    with pytest.raises(ValueError, match="Goal not found"):
        await archive_goal(9999)
