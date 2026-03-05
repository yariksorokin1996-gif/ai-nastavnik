"""E2E тест целей + Webapp API: E2E-4.

E2E-4: Фаза ЦЕЛЬ → создать цель → сгенерировать шаги → GET /api/user/goals/today → steps > 0.
"""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api import _rate_limits, app
from bot.goal_manager import create_goal, generate_steps
from bot.memory.database import update_user
from tests.e2e.conftest import E2E_TELEGRAM_ID


# ===========================================================================
# E2E-4: Цели + Webapp API
# ===========================================================================


class TestE2E4GoalsAndApi:
    """Цель + шаги через goal_manager → проверка через webapp API."""

    @pytest.fixture(autouse=True)
    def _clear_api_rate_limits(self):
        _rate_limits.clear()
        yield
        _rate_limits.clear()

    @pytest.fixture
    def mock_auth(self):
        """Мок авторизации Telegram для API."""
        with patch("backend.api.validate_init_data") as m:
            m.return_value = {
                "telegram_id": E2E_TELEGRAM_ID,
                "first_name": "Маша",
            }
            yield m

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "tma valid_init_data"}

    @pytest.mark.asyncio
    async def test_goal_steps_visible_in_api(
        self, e2e_user, mock_llm, mock_auth, auth_headers,
    ):
        """E2E-4: create_goal + generate_steps → API /goals/today возвращает шаги."""

        # Установить фазу ЦЕЛЬ
        await update_user(E2E_TELEGRAM_ID, current_phase="ЦЕЛЬ")

        # GPT mock для generate_steps
        mock_llm["goal_manager_gpt"].return_value = json.dumps({
            "steps": [
                {"title": "Позвонить маме", "deadline_days": 0},
                {"title": "Записаться к психологу", "deadline_days": 3},
                {"title": "Написать план", "deadline_days": 7},
            ]
        })

        # Создать цель
        goal = await create_goal(E2E_TELEGRAM_ID, "Улучшить отношения с мамой")
        assert goal.id is not None

        # Сгенерировать шаги
        steps = await generate_steps(goal.id, "Хочу наладить контакт с мамой")
        assert len(steps) == 3
        assert steps[0].title == "Позвонить маме"

        # Проверяем API: /api/user/goals/today
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/user/goals/today",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        # deadline_days=0 → шаг на сегодня
        assert len(data["steps"]) >= 1
        assert data["steps"][0]["title"] == "Позвонить маме"

    @pytest.mark.asyncio
    async def test_goals_list_in_api(
        self, e2e_user, mock_llm, mock_auth, auth_headers,
    ):
        """E2E-4b: GET /api/user/goals → цель + все 3 шага."""

        await update_user(E2E_TELEGRAM_ID, current_phase="ЦЕЛЬ")

        mock_llm["goal_manager_gpt"].return_value = json.dumps({
            "steps": [
                {"title": "Шаг 1", "deadline_days": 0},
                {"title": "Шаг 2", "deadline_days": 1},
            ]
        })

        goal = await create_goal(E2E_TELEGRAM_ID, "Моя цель")
        await generate_steps(goal.id, "Контекст")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/user/goals", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["goal"] is not None
        assert data["goal"]["title"] == "Моя цель"
        assert len(data["goal"]["steps"]) == 2
