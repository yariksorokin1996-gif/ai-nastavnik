"""
Тесты для bot/memory/episode_manager.py
9 тестов: create_episode, find_relevant_episodes, get_episode_titles.
Все database и LLM вызовы замоканы.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, patch

import pytest

from shared.llm_client import LLMError
from shared.models import Episode

# Промпт для .format() — фигурные скобки JSON должны быть экранированы
_TEST_SELECTION_PROMPT = (
    'Выбери конспекты.\n'
    'Сообщение: "{current_message}"\n'
    'Список:\n{episode_list}\n'
    'JSON: {{"selected": [номера]}}'
)


# ---------------------------------------------------------------------------
# create_episode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_create_episode_success(mock_gpt, mock_db):
    """create_episode вызывает call_gpt с EPISODE_SUMMARY_PROMPT, парсит JSON, сохраняет."""
    gpt_response = json.dumps({
        "title": "Разговор о маме",
        "summary": "Обсудили отношения с мамой",
        "emotional_tone": "тревога -> облегчение",
        "key_insight": "Мама тоже боится",
        "commitments": ["поговорить с мамой"],
        "techniques_worked": ["отражение слов"],
        "techniques_failed": [],
    })
    mock_gpt.return_value = gpt_response
    mock_db.create_episode = AsyncMock(return_value=42)

    from bot.memory.episode_manager import create_episode

    messages = [
        {"role": "user", "content": "Привет", "created_at": "2026-03-03 10:00:00"},
        {"role": "assistant", "content": "Привет!", "created_at": "2026-03-03 10:00:05"},
    ]

    result = await create_episode(111, messages)

    assert isinstance(result, Episode)
    assert result.title == "Разговор о маме"
    assert result.id == 42
    assert result.techniques_worked == ["отражение слов"]
    mock_gpt.assert_awaited_once()
    mock_db.create_episode.assert_awaited_once()


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_create_episode_empty_messages(mock_gpt, mock_db):
    """create_episode с пустыми messages возвращает Episode(title='Пустой разговор')."""
    mock_db.create_episode = AsyncMock()

    from bot.memory.episode_manager import create_episode

    result = await create_episode(111, [])

    assert isinstance(result, Episode)
    assert result.title == "Пустой разговор"
    mock_gpt.assert_not_awaited()
    mock_db.create_episode.assert_not_awaited()


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_create_episode_invalid_json_fallback(mock_gpt, mock_db):
    """create_episode: невалидный JSON от GPT -> fallback Episode(title='Разговор')."""
    mock_gpt.return_value = "это не JSON вообще {{"
    mock_db.create_episode = AsyncMock(return_value=1)

    from bot.memory.episode_manager import create_episode

    messages = [{"role": "user", "content": "Привет"}]
    result = await create_episode(111, messages)

    assert isinstance(result, Episode)
    assert result.title == "Разговор"


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_create_episode_llm_error_propagates(mock_gpt, mock_db):
    """create_episode: LLMError пробрасывается наверх."""
    mock_gpt.side_effect = LLMError("API unavailable")

    from bot.memory.episode_manager import create_episode

    messages = [{"role": "user", "content": "Привет"}]
    with pytest.raises(LLMError):
        await create_episode(111, messages)


# ---------------------------------------------------------------------------
# find_relevant_episodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.EPISODE_SELECTION_PROMPT", _TEST_SELECTION_PROMPT)
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_find_relevant_episodes_success(mock_gpt, mock_db):
    """find_relevant_episodes: GPT выбирает номера, маппит на реальные IDs."""
    headers = [
        {"id": 10, "title": "Разговор про маму", "created_at": "2026-03-01"},
        {"id": 20, "title": "Работа и усталость", "created_at": "2026-03-02"},
        {"id": 30, "title": "Цели на месяц", "created_at": "2026-03-03"},
    ]
    mock_db.get_episode_headers = AsyncMock(return_value=headers)

    # GPT выбирает номера 1 и 3 (1-based)
    mock_gpt.return_value = json.dumps({"selected": [1, 3]})

    # get_episodes_by_ids вернёт Episode-ы
    mock_db.get_episodes_by_ids = AsyncMock(return_value=[
        {
            "id": 10, "title": "Разговор про маму", "summary": "О маме",
            "emotional_tone": "тревога", "key_insight": None,
            "commitments_json": [], "techniques_worked_json": [],
            "techniques_failed_json": [],
        },
        {
            "id": 30, "title": "Цели на месяц", "summary": "Цели",
            "emotional_tone": "мотивация", "key_insight": "Нужен план",
            "commitments_json": [], "techniques_worked_json": [],
            "techniques_failed_json": [],
        },
    ])

    from bot.memory.episode_manager import find_relevant_episodes

    result = await find_relevant_episodes(111, "Мама звонила")

    assert len(result) == 2
    assert all(isinstance(ep, Episode) for ep in result)
    mock_db.get_episodes_by_ids.assert_awaited_once_with([10, 30])


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_find_relevant_episodes_empty_headers(mock_gpt, mock_db):
    """find_relevant_episodes: пустые headers -> []."""
    mock_db.get_episode_headers = AsyncMock(return_value=[])

    from bot.memory.episode_manager import find_relevant_episodes

    result = await find_relevant_episodes(111, "Любое сообщение")

    assert result == []
    mock_gpt.assert_not_awaited()


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.EPISODE_SELECTION_PROMPT", _TEST_SELECTION_PROMPT)
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_find_relevant_episodes_llm_error_keyword_fallback(mock_gpt, mock_db):
    """find_relevant_episodes: LLMError -> keyword fallback."""
    headers = [
        {"id": 10, "title": "Разговор про маму", "created_at": "2026-03-01"},
        {"id": 20, "title": "Работа и усталость", "created_at": "2026-03-02"},
    ]
    mock_db.get_episode_headers = AsyncMock(return_value=headers)
    mock_gpt.side_effect = LLMError("API error")
    mock_db.get_episodes_by_ids = AsyncMock(return_value=[
        {
            "id": 20, "title": "Работа и усталость", "summary": "О работе",
            "emotional_tone": "усталость", "key_insight": None,
            "commitments_json": [], "techniques_worked_json": [],
            "techniques_failed_json": [],
        },
    ])

    from bot.memory.episode_manager import find_relevant_episodes

    # "усталость" > 3 букв, совпадёт с "Работа и усталость"
    result = await find_relevant_episodes(111, "Чувствую усталость")

    assert len(result) >= 1


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.EPISODE_SELECTION_PROMPT", _TEST_SELECTION_PROMPT)
@patch("bot.memory.episode_manager.database")
@patch("bot.memory.episode_manager.call_gpt")
async def test_find_relevant_episodes_invalid_json_keyword_fallback(mock_gpt, mock_db):
    """find_relevant_episodes: невалидный JSON -> keyword fallback."""
    headers = [
        {"id": 10, "title": "Мама и конфликт", "created_at": "2026-03-01"},
    ]
    mock_db.get_episode_headers = AsyncMock(return_value=headers)
    mock_gpt.return_value = "не JSON"
    mock_db.get_episodes_by_ids = AsyncMock(return_value=[
        {
            "id": 10, "title": "Мама и конфликт", "summary": "О конфликте",
            "emotional_tone": "злость", "key_insight": None,
            "commitments_json": [], "techniques_worked_json": [],
            "techniques_failed_json": [],
        },
    ])

    from bot.memory.episode_manager import find_relevant_episodes

    # "конфликт" > 3 букв, совпадёт с "Мама и конфликт"
    result = await find_relevant_episodes(111, "Был конфликт")

    assert len(result) >= 1


# ---------------------------------------------------------------------------
# get_episode_titles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.episode_manager.database")
async def test_get_episode_titles(mock_db):
    """get_episode_titles возвращает список заголовков."""
    mock_db.get_episode_headers = AsyncMock(return_value=[
        {"id": 1, "title": "Первый", "created_at": "2026-03-01"},
        {"id": 2, "title": "Второй", "created_at": "2026-03-02"},
    ])

    from bot.memory.episode_manager import get_episode_titles

    result = await get_episode_titles(111)

    assert result == ["Первый", "Второй"]
