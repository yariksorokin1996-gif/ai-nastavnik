"""
Тесты для backend/api.py
23 теста: auth, rate limit, endpoints (user, goals, calendar, affirmation, analytics, delete).
Все database/LLM/goal_manager вызовы замоканы.
"""

import os
import sys
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api import _rate_limits, app
from shared.llm_client import LLMError

# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

TELEGRAM_ID = 123456


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Очищаем rate limits перед и после каждого теста."""
    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": "tma valid_init_data"}


@pytest.fixture
def mock_auth():
    with patch("backend.api.validate_init_data") as m:
        m.return_value = {"telegram_id": TELEGRAM_ID, "first_name": "Маша"}
        yield m


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _make_user_row(
    telegram_id=TELEGRAM_ID,
    name="Маша",
    current_phase="ЗНАКОМСТВО",
    messages_total=5,
):
    return {
        "telegram_id": telegram_id,
        "name": name,
        "current_phase": current_phase,
        "messages_total": messages_total,
    }


def _make_goal_step(
    step_id=1,
    goal_id=10,
    telegram_id=TELEGRAM_ID,
    title="Шаг 1",
    status="pending",
    deadline_at=None,
    completed_at=None,
):
    """Создает мок GoalStep с атрибутами-строками для совместимости с StepResponse."""
    mock = MagicMock()
    mock.id = step_id
    mock.goal_id = goal_id
    mock.telegram_id = telegram_id
    mock.title = title
    mock.status = status
    mock.sort_order = 0
    mock.deadline_at = deadline_at
    mock.completed_at = completed_at
    return mock


# ---------------------------------------------------------------------------
# 1. test_missing_auth -> 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_auth():
    """Запрос без Authorization header -> 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/user")
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 2. test_invalid_auth -> 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_auth():
    """Невалидный initData -> 401."""
    with patch("backend.api.validate_init_data") as m:
        m.return_value = None
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/user", headers={"Authorization": "tma invalid"}
            )
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3. test_rate_limit_exceeded -> 429 + Retry-After
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_exceeded(mock_auth, auth_headers):
    """60+ запросов за минуту -> 429 с Retry-After."""
    # Заполняем rate limit до предела
    now = time.monotonic()
    _rate_limits[TELEGRAM_ID] = [now] * 60

    with patch("backend.api.get_user", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user", headers=auth_headers)

    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "60"


# ---------------------------------------------------------------------------
# 4. test_get_user_existing -> 200 + правильные поля
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_existing(mock_auth, auth_headers):
    """Существующий пользователь -> 200 с данными."""
    user_row = _make_user_row()
    with patch("backend.api.get_user", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = user_row
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Маша"
    assert data["phase"] == "ЗНАКОМСТВО"
    assert data["sessions_count"] == 5
    assert data["telegram_id"] == TELEGRAM_ID


# ---------------------------------------------------------------------------
# 5. test_get_user_new -> создаёт пользователя + 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_new(mock_auth, auth_headers):
    """Новый пользователь -> create_user вызван, 200."""
    new_user = _make_user_row(messages_total=0)
    with (
        patch("backend.api.get_user", new_callable=AsyncMock) as mock_get,
        patch("backend.api.create_user", new_callable=AsyncMock) as mock_create,
    ):
        mock_get.return_value = None
        mock_create.return_value = new_user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user", headers=auth_headers)

    assert resp.status_code == 200
    mock_create.assert_called_once_with(TELEGRAM_ID, "Маша")


# ---------------------------------------------------------------------------
# 6. test_health_ok -> {status: "ok", db: true, uptime_s: float}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_ok():
    """Healthcheck: БД доступна -> status=ok, db=true."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=(1,))

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)
    # Поддерживаем async with для cursor
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    with patch("backend.api.get_db", mock_get_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] is True
    assert isinstance(data["uptime_s"], float)


# ---------------------------------------------------------------------------
# 7. test_health_db_error -> {status: "degraded", db: false}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_db_error():
    """Healthcheck: БД недоступна -> status=degraded, db=false."""

    @asynccontextmanager
    async def mock_get_db():
        raise RuntimeError("DB connection failed")
        yield  # noqa: RUF027 — unreachable yield needed for asynccontextmanager

    with patch("backend.api.get_db", mock_get_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["db"] is False


# ---------------------------------------------------------------------------
# 8. test_goals_with_active_goal -> goal + steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goals_with_active_goal(mock_auth, auth_headers):
    """Есть активная цель -> goal с шагами."""
    goal_row = {"id": 10, "title": "Моя цель", "status": "active"}
    steps_rows = [
        {
            "id": 1,
            "title": "Шаг 1",
            "status": "pending",
            "deadline_at": None,
            "completed_at": None,
        },
        {
            "id": 2,
            "title": "Шаг 2",
            "status": "done",
            "deadline_at": "2026-03-05",
            "completed_at": "2026-03-04",
        },
    ]
    with (
        patch("backend.api.get_active_goal", new_callable=AsyncMock) as mock_goal,
        patch("backend.api.get_goal_steps", new_callable=AsyncMock) as mock_steps,
    ):
        mock_goal.return_value = goal_row
        mock_steps.return_value = steps_rows
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/goals", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["goal"]["title"] == "Моя цель"
    assert len(data["goal"]["steps"]) == 2
    assert data["goal"]["steps"][1]["status"] == "done"


# ---------------------------------------------------------------------------
# 9. test_goals_no_active_goal -> {goal: null}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goals_no_active_goal(mock_auth, auth_headers):
    """Нет активной цели -> goal=null."""
    with patch("backend.api.get_active_goal", new_callable=AsyncMock) as mock_goal:
        mock_goal.return_value = None
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/goals", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["goal"] is None


# ---------------------------------------------------------------------------
# 10. test_today_steps_exist -> steps + counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_today_steps_exist(mock_auth, auth_headers):
    """Есть шаги на сегодня -> steps + completed_count/total_count."""
    steps = [
        _make_goal_step(step_id=1, title="Шаг 1", status="done"),
        _make_goal_step(step_id=2, title="Шаг 2", status="pending"),
        _make_goal_step(step_id=3, title="Шаг 3", status="done"),
    ]
    with patch(
        "backend.api.get_today_steps", new_callable=AsyncMock
    ) as mock_today:
        mock_today.return_value = steps
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/goals/today", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) == 3
    assert data["completed_count"] == 2
    assert data["total_count"] == 3


# ---------------------------------------------------------------------------
# 11. test_today_steps_empty -> {steps: [], completed_count: 0, total_count: 0}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_today_steps_empty(mock_auth, auth_headers):
    """Нет шагов на сегодня -> пустой ответ."""
    with patch(
        "backend.api.get_today_steps", new_callable=AsyncMock
    ) as mock_today:
        mock_today.return_value = []
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/goals/today", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["steps"] == []
    assert data["completed_count"] == 0
    assert data["total_count"] == 0


# ---------------------------------------------------------------------------
# 12. test_complete_step_success -> status: "done"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_step_success(mock_auth, auth_headers):
    """Завершение шага -> status=done."""
    step_row = {
        "telegram_id": TELEGRAM_ID,
        "id": 1,
        "goal_id": 10,
        "title": "Шаг",
        "status": "pending",
    }
    updated_step = _make_goal_step(step_id=1, status="done", completed_at="2026-03-04 12:00:00")
    with (
        patch("backend.api._get_step_by_id", new_callable=AsyncMock) as mock_get,
        patch("backend.api.complete_step", new_callable=AsyncMock) as mock_complete,
    ):
        mock_get.return_value = step_row
        mock_complete.return_value = updated_step
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/user/goals/steps/1",
                json={"status": "done"},
                headers=auth_headers,
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


# ---------------------------------------------------------------------------
# 13. test_skip_step_success -> status: "skipped"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_step_success(mock_auth, auth_headers):
    """Пропуск шага -> status=skipped."""
    step_row = {
        "telegram_id": TELEGRAM_ID,
        "id": 2,
        "goal_id": 10,
        "title": "Шаг",
        "status": "pending",
    }
    updated_step = _make_goal_step(
        step_id=2, status="skipped", completed_at="2026-03-04 12:00:00"
    )
    with (
        patch("backend.api._get_step_by_id", new_callable=AsyncMock) as mock_get,
        patch("backend.api.skip_step", new_callable=AsyncMock) as mock_skip,
    ):
        mock_get.return_value = step_row
        mock_skip.return_value = updated_step
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/user/goals/steps/2",
                json={"status": "skipped"},
                headers=auth_headers,
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


# ---------------------------------------------------------------------------
# 14. test_step_not_found -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_not_found(mock_auth, auth_headers):
    """Несуществующий step_id -> 404."""
    with patch("backend.api._get_step_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/user/goals/steps/9999",
                json={"status": "done"},
                headers=auth_headers,
            )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 15. test_step_forbidden -> 403 (другой юзер)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_forbidden(mock_auth, auth_headers):
    """Шаг принадлежит другому пользователю -> 403."""
    step_row = {
        "telegram_id": 999999,  # чужой юзер
        "id": 1,
        "goal_id": 10,
        "title": "Чужой шаг",
        "status": "pending",
    }
    with patch("backend.api._get_step_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = step_row
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/api/user/goals/steps/1",
                json={"status": "done"},
                headers=auth_headers,
            )

    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 16. test_step_invalid_status -> 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_invalid_status(mock_auth, auth_headers):
    """Невалидный статус (не done/skipped) -> 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/api/user/goals/steps/1",
            json={"status": "invalid_status"},
            headers=auth_headers,
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 17. test_calendar_with_data -> active_days, streak, total_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_with_data(mock_auth, auth_headers):
    """Календарь с данными -> active_days, streak, total_sessions."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(
        return_value=[("2026-03-04",), ("2026-03-03",), ("2026-03-02",)]
    )
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    user_row = _make_user_row(messages_total=42)

    with (
        patch("backend.api.get_db", mock_get_db),
        patch("backend.api.get_user", new_callable=AsyncMock) as mock_get_user,
    ):
        mock_get_user.return_value = user_row
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/calendar", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["active_days"], list)
    assert len(data["active_days"]) == 3
    assert data["total_sessions"] == 42
    assert isinstance(data["streak"], int)


# ---------------------------------------------------------------------------
# 18. test_calendar_empty -> пустой список, streak: 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_empty(mock_auth, auth_headers):
    """Пустой календарь -> active_days=[], streak=0."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    user_row = _make_user_row(messages_total=0)

    with (
        patch("backend.api.get_db", mock_get_db),
        patch("backend.api.get_user", new_callable=AsyncMock) as mock_get_user,
    ):
        mock_get_user.return_value = user_row
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/calendar", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["active_days"] == []
    assert data["streak"] == 0
    assert data["total_sessions"] == 0


# ---------------------------------------------------------------------------
# 19. test_affirmation_cached -> берёт из кеша (НЕ вызывает LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_affirmation_cached(mock_auth, auth_headers):
    """Аффирмация есть в кеше -> возвращает кешированную, LLM не вызывает."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(
        return_value=("Ты справишься!", "bank")
    )
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    with (
        patch("backend.api.get_db", mock_get_db),
        patch("backend.api.call_gpt", new_callable=AsyncMock) as mock_gpt,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/affirmation", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Ты справишься!"
    assert data["source"] == "bank"
    mock_gpt.assert_not_called()


# ---------------------------------------------------------------------------
# 20. test_affirmation_from_bank -> sessions_count < 7 -> банк
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_affirmation_from_bank(mock_auth, auth_headers):
    """sessions_count < 7 -> аффирмация из банка."""
    # Кеш пустой
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    user_row = _make_user_row(messages_total=3)

    with (
        patch("backend.api.get_db", mock_get_db),
        patch("backend.api.get_user", new_callable=AsyncMock) as mock_get_user,
        patch(
            "backend.api.create_daily_message", new_callable=AsyncMock
        ) as mock_save,
        patch("backend.api.call_gpt", new_callable=AsyncMock) as mock_gpt,
    ):
        mock_get_user.return_value = user_row
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/affirmation", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "bank"
    assert len(data["text"]) > 0
    mock_gpt.assert_not_called()
    mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# 21. test_affirmation_generated -> sessions_count >= 7 -> GPT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_affirmation_generated(mock_auth, auth_headers):
    """sessions_count >= 7 -> GPT генерация."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    user_row = _make_user_row(messages_total=10)

    with (
        patch("backend.api.get_db", mock_get_db),
        patch("backend.api.get_user", new_callable=AsyncMock) as mock_get_user,
        patch("backend.api.get_profile", new_callable=AsyncMock) as mock_profile,
        patch("backend.api.call_gpt", new_callable=AsyncMock) as mock_gpt,
        patch(
            "backend.api.create_daily_message", new_callable=AsyncMock
        ),
    ):
        mock_get_user.return_value = user_row
        mock_profile.return_value = None
        mock_gpt.return_value = "Ты сильнее, чем думаешь."
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/affirmation", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "generated"
    assert data["text"] == "Ты сильнее, чем думаешь."
    mock_gpt.assert_called_once()


# ---------------------------------------------------------------------------
# 22. test_affirmation_llm_error -> fallback на банк
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_affirmation_llm_error(mock_auth, auth_headers):
    """LLMError -> fallback на банк."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor)

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    user_row = _make_user_row(messages_total=10)

    with (
        patch("backend.api.get_db", mock_get_db),
        patch("backend.api.get_user", new_callable=AsyncMock) as mock_get_user,
        patch("backend.api.get_profile", new_callable=AsyncMock) as mock_profile,
        patch("backend.api.call_gpt", new_callable=AsyncMock) as mock_gpt,
        patch(
            "backend.api.create_daily_message", new_callable=AsyncMock
        ),
    ):
        mock_get_user.return_value = user_row
        mock_profile.return_value = None
        mock_gpt.side_effect = LLMError("API timeout")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/affirmation", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "bank"
    assert len(data["text"]) > 0


# ---------------------------------------------------------------------------
# 23. test_track_event -> 204
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_event(mock_auth, auth_headers):
    """POST /api/analytics/event -> 204."""
    with patch(
        "backend.api.add_webapp_event", new_callable=AsyncMock
    ) as mock_event:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/analytics/event",
                json={"event_type": "page_view", "page": "/home"},
                headers=auth_headers,
            )

    assert resp.status_code == 204
    mock_event.assert_called_once_with(
        telegram_id=TELEGRAM_ID,
        event_type="page_view",
        page="/home",
        metadata=None,
    )


# ---------------------------------------------------------------------------
# 24. test_delete_user -> {ok: true}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_user(mock_auth, auth_headers):
    """DELETE /api/user -> {ok: true}."""
    with patch(
        "backend.api.delete_user_completely", new_callable=AsyncMock
    ) as mock_del:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete("/api/user", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_del.assert_called_once_with(TELEGRAM_ID)
