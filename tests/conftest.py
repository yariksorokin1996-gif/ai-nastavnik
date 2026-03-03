"""Базовые фикстуры для тестов проекта Ева."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Один event loop на всю сессию тестов."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db(tmp_path):
    """In-memory SQLite с WAL mode."""
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
        yield conn


@pytest.fixture
def mock_claude():
    """Мок для call_claude (Claude Sonnet)."""
    mock = AsyncMock()
    mock.return_value = "Привет! Расскажи, что у тебя сейчас происходит?"
    return mock


@pytest.fixture
def mock_gpt():
    """Мок для call_gpt (GPT-4o-mini)."""
    mock = AsyncMock()
    mock.return_value = '{"recommendation": "stay", "confidence": 0.5}'
    return mock


@pytest.fixture
def test_user():
    """Тестовый пользователь."""
    return {
        "telegram_id": 123456789,
        "name": "Маша",
        "phase": "ЗНАКОМСТВО",
        "messages_total": 0,
        "created_at": "2026-03-03T10:00:00",
    }


@pytest.fixture
def mock_bot():
    """Мок Telegram-бота."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot
