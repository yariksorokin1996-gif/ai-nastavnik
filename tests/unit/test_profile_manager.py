"""
Тесты для bot/memory/profile_manager.py
11 тестов: create_empty_profile, get_profile, update_profile,
           rollback_profile, get_profile_as_text.
Все database-вызовы замоканы.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, patch

import pytest

from shared.models import ProfileDiff, SemanticProfile


# ---------------------------------------------------------------------------
# create_empty_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_create_empty_profile(mock_db):
    """create_empty_profile возвращает пустой SemanticProfile и вызывает upsert_profile."""
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import create_empty_profile

    result = await create_empty_profile(telegram_id=111)

    assert isinstance(result, SemanticProfile)
    assert result.name is None
    assert result.people == []
    mock_db.upsert_profile.assert_awaited_once()
    call_args = mock_db.upsert_profile.call_args
    # Проверяем telegram_id и tokens_count (могут быть позиционные или kwargs)
    args, kwargs = call_args
    assert args[0] == 111  # telegram_id
    # tokens_count может быть 2-м позиционным или keyword
    if len(args) > 2:
        assert args[2] == 0
    else:
        assert kwargs.get("tokens_count") == 0


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_get_profile_returns_semantic_profile(mock_db):
    """get_profile возвращает SemanticProfile из dict."""
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {"name": "Маша", "age": 28, "city": "Москва"},
    })

    from bot.memory.profile_manager import get_profile

    result = await get_profile(111)

    assert isinstance(result, SemanticProfile)
    assert result.name == "Маша"
    assert result.age == 28
    assert result.city == "Москва"


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_get_profile_none_when_not_found(mock_db):
    """get_profile возвращает None если профиль не найден."""
    mock_db.get_profile = AsyncMock(return_value=None)

    from bot.memory.profile_manager import get_profile

    result = await get_profile(111)
    assert result is None


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_get_profile_none_on_invalid_json(mock_db):
    """get_profile возвращает None при невалидном JSON (ValidationError)."""
    # age должен быть int, но передаём невалидный тип через невалидный people
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {"people": "не список, а строка"},
    })

    from bot.memory.profile_manager import get_profile

    result = await get_profile(111)
    assert result is None


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_update_profile_set_fields(mock_db):
    """update_profile применяет set_fields."""
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {"name": "Маша"},
    })
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import update_profile

    diff = ProfileDiff(set_fields={"city": "Питер", "age": 30})
    result = await update_profile(111, diff)

    assert result.city == "Питер"
    assert result.age == 30
    assert result.name == "Маша"
    mock_db.upsert_profile.assert_awaited_once()


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_update_profile_add_to_lists_no_duplicates(mock_db):
    """update_profile: add_to_lists extend без дублей."""
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {"triggers": ["конфликт"]},
    })
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import update_profile

    diff = ProfileDiff(add_to_lists={"triggers": ["конфликт", "критика"]})
    result = await update_profile(111, diff)

    assert result.triggers == ["конфликт", "критика"]


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_update_profile_people_dedup_by_name(mock_db):
    """update_profile: people дедупликация по name (обновление)."""
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {
            "people": [{"name": "Саша", "relation": "друг"}],
        },
    })
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import update_profile

    diff = ProfileDiff(add_to_lists={
        "people": [
            {"name": "Саша", "relation": "муж"},  # обновление
            {"name": "Настя", "relation": "подруга"},  # новый
        ],
    })
    result = await update_profile(111, diff)

    assert len(result.people) == 2
    names = {p.name: p.relation for p in result.people}
    assert names["Саша"] == "муж"  # обновлён
    assert names["Настя"] == "подруга"  # добавлен


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_update_profile_empty_diff_noop(mock_db):
    """update_profile: пустой diff -> no-op, upsert_profile НЕ вызван."""
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {"name": "Маша"},
    })
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import update_profile

    diff = ProfileDiff()  # пустой diff
    result = await update_profile(111, diff)

    assert result.name == "Маша"
    mock_db.upsert_profile.assert_not_awaited()


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_update_profile_creates_empty_when_not_found(mock_db):
    """update_profile: создаёт пустой профиль если не найден, затем применяет diff."""
    mock_db.get_profile = AsyncMock(return_value=None)
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import update_profile

    diff = ProfileDiff(set_fields={"name": "Маша"})
    result = await update_profile(111, diff)
    assert result.name == "Маша"
    # upsert_profile вызван дважды: create_empty_profile + save в update_profile
    assert mock_db.upsert_profile.call_count == 2


# ---------------------------------------------------------------------------
# rollback_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_rollback_profile_restores_version(mock_db):
    """rollback_profile восстанавливает указанную версию."""
    mock_db.get_profile_version = AsyncMock(return_value={
        "name": "Маша", "city": "Москва",
    })
    mock_db.upsert_profile = AsyncMock()

    from bot.memory.profile_manager import rollback_profile

    result = await rollback_profile(111, version=1)

    assert isinstance(result, SemanticProfile)
    assert result.name == "Маша"
    assert result.city == "Москва"
    mock_db.upsert_profile.assert_awaited_once()


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_rollback_profile_raises_when_version_not_found(mock_db):
    """rollback_profile: ValueError если версия не найдена."""
    mock_db.get_profile_version = AsyncMock(return_value=None)

    from bot.memory.profile_manager import rollback_profile

    with pytest.raises(ValueError, match="Version 99 not found"):
        await rollback_profile(111, version=99)


# ---------------------------------------------------------------------------
# get_profile_as_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.profile_manager.database")
async def test_get_profile_as_text_format(mock_db):
    """get_profile_as_text: формат '=== ПРОФИЛЬ ===' и пропуск None-полей."""
    mock_db.get_profile = AsyncMock(return_value={
        "profile_json": {
            "name": "Маша",
            "age": 28,
            "city": None,  # пропускается
            "triggers": ["конфликт", "критика"],
        },
    })

    from bot.memory.profile_manager import get_profile_as_text

    result = await get_profile_as_text(111)

    assert result.startswith("=== ПРОФИЛЬ ===")
    assert "Имя: Маша" in result
    assert "Возраст: 28" in result
    assert "Город" not in result  # None пропущен
    assert "Триггеры: конфликт, критика" in result
