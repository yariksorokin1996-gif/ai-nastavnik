"""Фикстуры для E2E тестов.

E2E = реальная БД (17 таблиц) + мокированные LLM (call_claude + call_gpt).
Все 8 точек вызова LLM патчатся через mock_llm.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bot.memory.database import (
    create_user,
    init_db,
)
from bot.session_manager import process_message


# ---------------------------------------------------------------------------
# real_db: реальная БД с 17 таблицами (autouse)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def real_db(tmp_path, monkeypatch):
    """Создаёт реальную БД на каждый тест (tmp_path)."""
    db_path = str(tmp_path / "e2e_test.db")
    monkeypatch.setattr("bot.memory.database.DB_PATH", db_path)
    monkeypatch.setattr("shared.config.DB_PATH", db_path)
    await init_db()
    yield db_path


# ---------------------------------------------------------------------------
# clear_module_state: сброс глобального состояния (autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_module_state():
    """Очищает модуль-уровневое состояние перед каждым тестом."""
    from bot.analytics.alerter import alerter
    from bot.memory.full_memory_update import _error_counts
    from bot.session_manager import (
        _consecutive_errors,
        _rate_counters,
        _user_locks,
    )

    _user_locks.clear()
    _rate_counters.clear()
    _consecutive_errors.clear()
    _error_counts.clear()
    alerter._counters.clear()
    alerter._last_alert.clear()
    alerter._bot = None

    yield

    _user_locks.clear()
    _rate_counters.clear()
    _consecutive_errors.clear()
    _error_counts.clear()
    alerter._counters.clear()
    alerter._last_alert.clear()
    alerter._bot = None


# ---------------------------------------------------------------------------
# mock_llm: патчит call_claude и call_gpt во ВСЕХ модулях (autouse)
# ---------------------------------------------------------------------------

# Все точки импорта LLM-функций в проекте:
_LLM_PATCHES = {
    # call_claude
    "session_manager_claude": "bot.session_manager.call_claude",
    # call_gpt (8 точек)
    "full_memory_update_gpt": "bot.memory.full_memory_update.call_gpt",
    "episode_manager_gpt": "bot.memory.episode_manager.call_gpt",
    "phase_evaluator_gpt": "bot.prompts.phase_evaluator.call_gpt",
    "goal_manager_gpt": "bot.goal_manager.call_gpt",
    "daily_messenger_gpt": "bot.daily_messenger.call_gpt",
    "safety_gpt": "shared.safety.call_gpt",
    "api_gpt": "backend.api.call_gpt",
}


@pytest.fixture(autouse=True)
def mock_llm():
    """Патчит ВСЕ LLM-вызовы. Возвращает dict[str, AsyncMock] по ключам."""
    mocks = {}
    patchers = []

    for key, target in _LLM_PATCHES.items():
        p = patch(target, new_callable=AsyncMock)
        mock = p.start()
        patchers.append(p)
        mocks[key] = mock

    # Дефолтные ответы (безопасные)
    mocks["session_manager_claude"].return_value = (
        "Привет! Расскажи, что у тебя сейчас происходит?"
    )
    mocks["phase_evaluator_gpt"].return_value = (
        '{"recommendation": "stay", "confidence": 0.3, "criteria_met": []}'
    )
    mocks["episode_manager_gpt"].return_value = '{"episode_ids": []}'
    mocks["full_memory_update_gpt"].return_value = (
        '{"set_fields": {}, "add_to_lists": {}, "remove_fields": []}'
    )
    mocks["goal_manager_gpt"].return_value = '{"steps": []}'
    mocks["daily_messenger_gpt"].return_value = "Доброе утро!"
    mocks["safety_gpt"].return_value = '{"is_crisis": false, "level": 0}'
    mocks["api_gpt"].return_value = "Ты справишься!"

    yield mocks

    for p in patchers:
        p.stop()


# ---------------------------------------------------------------------------
# e2e_user: тестовый пользователь в реальной БД
# ---------------------------------------------------------------------------

E2E_TELEGRAM_ID = 999999


@pytest_asyncio.fixture
async def e2e_user():
    """Создаёт пользователя Маша с telegram_id=999999."""
    await create_user(E2E_TELEGRAM_ID, name="Маша")
    return {"telegram_id": E2E_TELEGRAM_ID, "name": "Маша"}


# ---------------------------------------------------------------------------
# mock_bot: мок Telegram-бота
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bot():
    """Мок Telegram-бота для alerter и feedback_collector."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


async def send_messages(
    telegram_id: int,
    count: int,
    mock_claude: AsyncMock,
    texts: list[str] | None = None,
    start_msg_id: int = 100,
) -> list[str]:
    """Отправляет N сообщений через process_message.

    Args:
        telegram_id: ID пользователя.
        count: Количество сообщений.
        mock_claude: Мок call_claude для настройки ответов.
        texts: Список текстов (если None, генерирует "Сообщение N").
        start_msg_id: Начальный message_id (уникальные для idempotency).

    Returns:
        Список ответов Евы.
    """
    responses = []
    for i in range(count):
        text = texts[i] if texts and i < len(texts) else f"Сообщение {i + 1}"
        resp = await process_message(
            telegram_id=telegram_id,
            message_id=start_msg_id + i,
            text=text,
            user_name="Маша",
        )
        responses.append(resp)
    return responses


def time_ago(minutes: int) -> str:
    """Возвращает ISO datetime строку N минут назад (UTC)."""
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


