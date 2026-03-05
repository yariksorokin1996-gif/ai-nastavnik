"""
Тесты для bot/memory/full_memory_update.py
10 тестов: no_users, no_messages, full_success, episode_error, profile_error,
           pending_facts_cleared, error_counter_3, profile_no_diff,
           procedural_with_techniques, duplicate_episode_protection.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import logging
from unittest.mock import AsyncMock, patch

import pytest

from shared.llm_client import LLMError
from shared.models import Episode, FullUpdateResult, SemanticProfile


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

_SAMPLE_USER = {
    "telegram_id": 123,
    "last_full_update_at": "2026-03-04 10:00:00",
}

_SAMPLE_MESSAGES = [
    {"role": "user", "content": "Привет", "created_at": "2026-03-04 10:30:00"},
    {"role": "assistant", "content": "Привет!", "created_at": "2026-03-04 10:30:05"},
]

_SAMPLE_EPISODE = Episode(
    id=42,
    title="Разговор о настроении",
    summary="Обсудили текущее состояние",
    emotional_tone="нейтрально → спокойствие",
    key_insight=None,
    commitments=[],
    techniques_worked=["отражение слов"],
    techniques_failed=["давление на действие"],
)

_SAMPLE_PROFILE = SemanticProfile(name="Маша", age=28)

_GPT_PROFILE_DIFF = json.dumps({
    "set_fields": {"city": "Москва"},
    "add_to_lists": {},
    "remove_fields": [],
})

_GPT_PROFILE_NO_DIFF = json.dumps({
    "set_fields": {},
    "add_to_lists": {},
    "remove_fields": [],
})

_SAMPLE_FACTS = [
    {"fact_type": "name", "content": "Маша", "confidence": "high"},
    {"fact_type": "age", "content": "28", "confidence": "high"},
]


def _make_mock_db(
    users=None,
    user=None,
    messages=None,
    facts=None,
    headers=None,
):
    """Создаёт настроенный mock для database."""
    mock = AsyncMock()
    mock.get_users_needing_update = AsyncMock(
        return_value=users if users is not None else [123]
    )
    mock.get_user = AsyncMock(
        return_value=user if user is not None else dict(_SAMPLE_USER)
    )
    mock.get_messages_since = AsyncMock(
        return_value=messages if messages is not None else list(_SAMPLE_MESSAGES)
    )
    mock.get_pending_facts = AsyncMock(
        return_value=facts if facts is not None else []
    )
    mock.get_episode_headers = AsyncMock(
        return_value=headers if headers is not None else []
    )
    mock.get_episodes_by_ids = AsyncMock(return_value=[])
    mock.clear_pending_facts = AsyncMock()
    mock.update_user = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# 1. test_no_users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.database")
async def test_no_users(mock_db):
    """get_users_needing_update returns [] -> пустой список результатов."""
    mock_db.get_users_needing_update = AsyncMock(return_value=[])

    from bot.memory.full_memory_update import run_full_memory_update

    results = await run_full_memory_update()

    assert results == []
    mock_db.get_users_needing_update.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. test_no_messages_early_exit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_no_messages_early_exit(mock_db, mock_ep, mock_prof, mock_proc, mock_gpt):
    """Нет новых сообщений -> needs_full_update=0, episode_id=None."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=[])
    mock_db.update_user = AsyncMock()

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    assert isinstance(result, FullUpdateResult)
    assert result.telegram_id == 123
    assert result.episode_id is None
    assert result.error is None
    assert result.profile_updated is False
    mock_db.update_user.assert_awaited_once()
    # Проверяем, что needs_full_update=0 передан
    call_kwargs = mock_db.update_user.call_args
    assert call_kwargs[1].get("needs_full_update") == 0 or \
        (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 0)
    assert not mock_ep.create_episode.called
    assert not mock_gpt.called


# ---------------------------------------------------------------------------
# 3. test_full_success_5_steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_full_success_5_steps(mock_db, mock_ep, mock_prof, mock_proc, mock_gpt):
    """Happy path: все 5 шагов успешны."""
    # Step 1: user + messages
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])
    mock_db.get_pending_facts = AsyncMock(return_value=list(_SAMPLE_FACTS))
    mock_db.clear_pending_facts = AsyncMock()
    mock_db.update_user = AsyncMock()

    # Step 2: episode
    mock_ep.create_episode = AsyncMock(return_value=_SAMPLE_EPISODE)

    # Step 3: profile
    mock_prof.get_profile = AsyncMock(return_value=_SAMPLE_PROFILE)
    mock_prof.update_profile = AsyncMock(return_value=_SAMPLE_PROFILE)
    mock_gpt.return_value = _GPT_PROFILE_DIFF

    # Step 4: procedural
    mock_proc.update_procedural = AsyncMock()

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    assert result.telegram_id == 123
    assert result.episode_id == 42
    assert result.profile_updated is True
    assert result.procedural_updated is True
    assert result.pending_facts_processed == 2
    assert result.error is None

    # Verify calls
    mock_ep.create_episode.assert_awaited_once_with(123, list(_SAMPLE_MESSAGES))
    mock_prof.update_profile.assert_awaited_once()
    mock_proc.update_procedural.assert_awaited_once()
    mock_db.clear_pending_facts.assert_awaited_once_with(123)
    mock_gpt.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4. test_episode_creation_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_episode_creation_error(mock_db, mock_ep, mock_prof, mock_proc, mock_gpt):
    """create_episode raises LLMError -> result.error set, needs_full_update stays 1."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])
    mock_db.update_user = AsyncMock()

    mock_ep.create_episode = AsyncMock(side_effect=LLMError("GPT timeout"))

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    assert result.error == "GPT timeout"
    assert result.episode_id is None
    assert result.profile_updated is False
    assert result.procedural_updated is False
    # needs_full_update НЕ сброшен (update_user не вызван с needs_full_update=0
    # после early return)
    assert not mock_prof.update_profile.called
    assert not mock_proc.update_procedural.called
    assert not mock_db.clear_pending_facts.called


# ---------------------------------------------------------------------------
# 5. test_profile_update_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_profile_update_error(mock_db, mock_ep, mock_prof, mock_proc, mock_gpt):
    """call_gpt raises LLMError on step 3 -> episode_id set, profile_updated=False."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])
    mock_db.get_pending_facts = AsyncMock(return_value=[])
    mock_db.clear_pending_facts = AsyncMock()
    mock_db.update_user = AsyncMock()

    # Step 2 OK
    mock_ep.create_episode = AsyncMock(return_value=_SAMPLE_EPISODE)
    # Step 3 FAIL
    mock_prof.get_profile = AsyncMock(return_value=_SAMPLE_PROFILE)
    mock_gpt.side_effect = LLMError("profile update timeout")
    # Step 4 — episode has techniques
    mock_proc.update_procedural = AsyncMock()

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    assert result.episode_id == 42
    assert result.profile_updated is False
    assert result.error == "profile update timeout"
    # Step 4 still runs (procedural update from episode techniques)
    mock_proc.update_procedural.assert_awaited_once()
    assert result.procedural_updated is True
    # Step 5 still runs
    mock_db.clear_pending_facts.assert_awaited_once()


# ---------------------------------------------------------------------------
# 6. test_pending_facts_cleared
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_pending_facts_cleared(mock_db, mock_ep, mock_prof, mock_proc, mock_gpt):
    """Verify clear_pending_facts called after success."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])
    mock_db.get_pending_facts = AsyncMock(return_value=list(_SAMPLE_FACTS))
    mock_db.clear_pending_facts = AsyncMock()
    mock_db.update_user = AsyncMock()

    episode_no_tech = Episode(
        id=10, title="Test", summary="Test", emotional_tone="ok",
    )
    mock_ep.create_episode = AsyncMock(return_value=episode_no_tech)
    mock_prof.get_profile = AsyncMock(return_value=None)
    mock_gpt.return_value = _GPT_PROFILE_NO_DIFF

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    mock_db.clear_pending_facts.assert_awaited_once_with(123)
    assert result.pending_facts_processed == 2


# ---------------------------------------------------------------------------
# 7. test_error_counter_3_errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_error_counter_3_errors(
    mock_db, mock_ep, mock_prof, mock_proc, mock_gpt, caplog
):
    """3 consecutive errors -> logger.error called on 3rd."""
    import bot.memory.full_memory_update as fmu

    # Reset error counts
    fmu._error_counts.clear()

    mock_db.get_users_needing_update = AsyncMock(return_value=[999])
    mock_db.get_user = AsyncMock(return_value={"telegram_id": 999, "last_full_update_at": None})
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])

    mock_ep.create_episode = AsyncMock(side_effect=LLMError("timeout"))

    # Вызываем 3 раза
    with caplog.at_level(logging.ERROR, logger="bot.memory.full_memory_update"):
        await fmu.run_full_memory_update()
        await fmu.run_full_memory_update()
        await fmu.run_full_memory_update()

    # На 3-м вызове должен быть logger.error с "3 consecutive"
    error_messages = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("3 consecutive" in msg for msg in error_messages), (
        f"Expected '3 consecutive' in error logs, got: {error_messages}"
    )

    # Cleanup
    fmu._error_counts.clear()


# ---------------------------------------------------------------------------
# 8. test_profile_no_diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_profile_no_diff(mock_db, mock_ep, mock_prof, mock_proc, mock_gpt):
    """GPT returns empty diff -> profile_updated=False, update_profile NOT called."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])
    mock_db.get_pending_facts = AsyncMock(return_value=[])
    mock_db.clear_pending_facts = AsyncMock()
    mock_db.update_user = AsyncMock()

    episode_no_tech = Episode(
        id=10, title="Test", summary="Test", emotional_tone="ok",
    )
    mock_ep.create_episode = AsyncMock(return_value=episode_no_tech)
    mock_prof.get_profile = AsyncMock(return_value=_SAMPLE_PROFILE)
    mock_gpt.return_value = _GPT_PROFILE_NO_DIFF

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    assert result.profile_updated is False
    assert not mock_prof.update_profile.called
    assert result.error is None


# ---------------------------------------------------------------------------
# 9. test_procedural_with_techniques
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_procedural_with_techniques(
    mock_db, mock_ep, mock_prof, mock_proc, mock_gpt
):
    """Episode has techniques_worked -> update_procedural called."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    mock_db.get_episode_headers = AsyncMock(return_value=[])
    mock_db.get_pending_facts = AsyncMock(return_value=[])
    mock_db.clear_pending_facts = AsyncMock()
    mock_db.update_user = AsyncMock()

    mock_ep.create_episode = AsyncMock(return_value=_SAMPLE_EPISODE)
    mock_prof.get_profile = AsyncMock(return_value=_SAMPLE_PROFILE)
    mock_gpt.return_value = _GPT_PROFILE_NO_DIFF
    mock_proc.update_procedural = AsyncMock()

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    assert result.procedural_updated is True
    mock_proc.update_procedural.assert_awaited_once_with(
        123,
        {
            "what_works": ["отражение слов"],
            "what_doesnt": ["давление на действие"],
        },
    )


# ---------------------------------------------------------------------------
# 10. test_duplicate_episode_protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.full_memory_update.call_gpt")
@patch("bot.memory.full_memory_update.procedural_memory")
@patch("bot.memory.full_memory_update.profile_manager")
@patch("bot.memory.full_memory_update.episode_manager")
@patch("bot.memory.full_memory_update.database")
async def test_duplicate_episode_protection(
    mock_db, mock_ep, mock_prof, mock_proc, mock_gpt
):
    """get_episode_headers returns episode with recent created_at -> create_episode NOT called."""
    mock_db.get_user = AsyncMock(return_value=dict(_SAMPLE_USER))
    mock_db.get_messages_since = AsyncMock(return_value=list(_SAMPLE_MESSAGES))
    # Эпизод уже существует, created_at >= last_full_update_at
    mock_db.get_episode_headers = AsyncMock(return_value=[
        {"id": 99, "title": "Existing episode", "created_at": "2026-03-04 10:35:00"},
    ])
    mock_db.get_episodes_by_ids = AsyncMock(return_value=[
        {
            "id": 99,
            "title": "Existing episode",
            "summary": "Existing summary",
            "techniques_worked_json": [],
            "techniques_failed_json": [],
        },
    ])
    mock_db.get_pending_facts = AsyncMock(return_value=[])
    mock_db.clear_pending_facts = AsyncMock()
    mock_db.update_user = AsyncMock()

    mock_prof.get_profile = AsyncMock(return_value=_SAMPLE_PROFILE)
    mock_gpt.return_value = _GPT_PROFILE_NO_DIFF

    from bot.memory.full_memory_update import update_single_user

    result = await update_single_user(123)

    # create_episode НЕ вызван — использован существующий
    assert not mock_ep.create_episode.called
    assert result.episode_id == 99
    assert result.error is None
