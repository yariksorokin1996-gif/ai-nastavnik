"""
Тесты для bot/memory/procedural_memory.py
8 тестов: get_procedural, update_procedural, get_procedural_as_text.
Все database-вызовы замоканы.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, patch

import pytest

from shared.models import ProceduralMemory


# ---------------------------------------------------------------------------
# get_procedural
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_get_procedural_returns_model(mock_db):
    """get_procedural возвращает ProceduralMemory из dict."""
    mock_db.get_procedural = AsyncMock(return_value={
        "memory_json": {
            "what_works": ["мягкие вопросы"],
            "what_doesnt": ["давление"],
            "communication_style": {"tone": "тёплый"},
        },
    })

    from bot.memory.procedural_memory import get_procedural

    result = await get_procedural(111)

    assert isinstance(result, ProceduralMemory)
    assert result.what_works == ["мягкие вопросы"]
    assert result.what_doesnt == ["давление"]
    assert result.communication_style == {"tone": "тёплый"}


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_get_procedural_none_when_not_found(mock_db):
    """get_procedural возвращает None если нет записи."""
    mock_db.get_procedural = AsyncMock(return_value=None)

    from bot.memory.procedural_memory import get_procedural

    result = await get_procedural(111)
    assert result is None


# ---------------------------------------------------------------------------
# update_procedural
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_update_procedural_merge_what_works_no_dupes(mock_db):
    """update_procedural: merge what_works без дублей."""
    mock_db.get_procedural = AsyncMock(return_value={
        "memory_json": {
            "what_works": ["мягкие вопросы"],
            "what_doesnt": [],
            "communication_style": {},
        },
    })
    mock_db.upsert_procedural = AsyncMock()

    from bot.memory.procedural_memory import update_procedural

    result = await update_procedural(111, {
        "what_works": ["мягкие вопросы", "отражение слов"],
    })

    assert isinstance(result, ProceduralMemory)
    assert result.what_works == ["мягкие вопросы", "отражение слов"]
    mock_db.upsert_procedural.assert_awaited_once()


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_update_procedural_merge_what_doesnt_no_dupes(mock_db):
    """update_procedural: merge what_doesnt без дублей."""
    mock_db.get_procedural = AsyncMock(return_value={
        "memory_json": {
            "what_works": [],
            "what_doesnt": ["давление"],
            "communication_style": {},
        },
    })
    mock_db.upsert_procedural = AsyncMock()

    from bot.memory.procedural_memory import update_procedural

    result = await update_procedural(111, {
        "what_doesnt": ["давление", "два вопроса подряд"],
    })

    assert result.what_doesnt == ["давление", "два вопроса подряд"]


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_update_procedural_communication_style_update(mock_db):
    """update_procedural: communication_style dict.update."""
    mock_db.get_procedural = AsyncMock(return_value={
        "memory_json": {
            "what_works": [],
            "what_doesnt": [],
            "communication_style": {"tone": "тёплый"},
        },
    })
    mock_db.upsert_procedural = AsyncMock()

    from bot.memory.procedural_memory import update_procedural

    result = await update_procedural(111, {
        "communication_style": {"humor": "лёгкий", "tone": "мягкий"},
    })

    assert result.communication_style == {
        "tone": "мягкий",   # обновлён
        "humor": "лёгкий",  # добавлен
    }


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_update_procedural_empty_updates_noop(mock_db):
    """update_procedural: пустой updates -> no-op, upsert НЕ вызван."""
    mock_db.get_procedural = AsyncMock(return_value={
        "memory_json": {
            "what_works": ["а"],
            "what_doesnt": [],
            "communication_style": {},
        },
    })
    mock_db.upsert_procedural = AsyncMock()

    from bot.memory.procedural_memory import update_procedural

    result = await update_procedural(111, {})

    assert isinstance(result, ProceduralMemory)
    mock_db.upsert_procedural.assert_not_awaited()


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_update_procedural_creates_new_when_none(mock_db):
    """update_procedural: нет текущей записи -> создать новую."""
    mock_db.get_procedural = AsyncMock(return_value=None)
    mock_db.upsert_procedural = AsyncMock()

    from bot.memory.procedural_memory import update_procedural

    result = await update_procedural(111, {
        "what_works": ["валидация"],
    })

    assert isinstance(result, ProceduralMemory)
    assert result.what_works == ["валидация"]
    mock_db.upsert_procedural.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_procedural_as_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_get_procedural_as_text_format(mock_db):
    """get_procedural_as_text: формат '=== КАК С НЕЙ РАБОТАТЬ ===', пропуск пустых секций."""
    mock_db.get_procedural = AsyncMock(return_value={
        "memory_json": {
            "what_works": ["мягкие вопросы", "валидация"],
            "what_doesnt": [],  # пустое -> пропускается
            "communication_style": {"tone": "тёплый"},
        },
    })

    from bot.memory.procedural_memory import get_procedural_as_text

    result = await get_procedural_as_text(111)

    assert "=== КАК С НЕЙ РАБОТАТЬ ===" in result
    assert "мягкие вопросы" in result
    assert "валидация" in result
    assert "Не работает" not in result  # пустой what_doesnt пропущен
    assert "tone: тёплый" in result


@pytest.mark.asyncio
@patch("bot.memory.procedural_memory.database")
async def test_get_procedural_as_text_none_returns_empty(mock_db):
    """get_procedural_as_text: None -> пустая строка."""
    mock_db.get_procedural = AsyncMock(return_value=None)

    from bot.memory.procedural_memory import get_procedural_as_text

    result = await get_procedural_as_text(111)
    assert result == ""
