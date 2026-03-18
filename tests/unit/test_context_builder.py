"""Тесты для bot/memory/context_builder.py. 12 тестов."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, patch

import pytest

from shared.models import Episode


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

_BASE_USER = {
    "telegram_id": 111,
    "current_phase": "ЗНАКОМСТВО",
    "last_message_at": None,
    "messages_total": 0,
}

_ACTIVE_USER = {
    "telegram_id": 222,
    "current_phase": "ЗЕРКАЛО",
    "last_message_at": "2026-03-01 10:00:00",
    "messages_total": 25,
}

_SAMPLE_EPISODES = [
    Episode(
        id=1,
        title="Разговор про работу",
        summary="Обсуждали проблемы на работе",
        emotional_tone="тревога → облегчение",
        key_insight="Понимает что боится отказа",
    ),
    Episode(
        id=2,
        title="Про маму",
        summary="Отношения с мамой",
        emotional_tone="грусть → принятие",
        key_insight=None,
    ),
]

_SAMPLE_PATTERNS = [
    {"pattern_text": "Избегает конфликтов", "count": 5},
    {"pattern_text": "Обесценивает свои достижения", "count": 3},
]

_SAMPLE_GOAL = {"id": 1, "title": "Научиться говорить нет"}

_SAMPLE_STEPS = [
    {"title": "Отказать коллеге", "status": "pending", "deadline_at": None},
    {"title": "Поговорить с мамой", "status": "completed", "deadline_at": None},
]

# Длинный base prompt (~1600 токенов) для тестов обрезки
_LONG_BASE = "Ты — Ева. " * 500


def _default_patches():
    """Возвращает словарь дефолтных return_value для моков."""
    return {
        "db_get_user": _BASE_USER.copy(),
        "profile": "",
        "procedural": "",
        "episodes": [],
        "patterns": [],
        "goal": None,
        "bsp": "Ты — Ева. Тёплая, мудрая подруга. ЗНАКОМСТВО",
    }


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_new_user_basic(mock_db, mock_prof, mock_eps, mock_proc, mock_bsp):
    """Новый юзер (пустая память): was_truncated=False, fallback-профиль, token_count > 0."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.return_value = ""
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. Тёплая подруга. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    prompt, token_count, meta = await build_context(111, "Привет")

    assert meta.was_truncated is False
    assert "Новый пользователь" in prompt
    assert token_count > 0


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_new_user_procedural_fallback(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """Новый юзер: procedural пуст -> fallback 'Стиль не определён' в промпте."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.return_value = ""
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    prompt, _, meta = await build_context(111, "Привет")

    assert "Стиль не определён" in prompt
    assert "procedural" in meta.filled_vars


@pytest.mark.asyncio
async def test_profile_truncation_removes_strengths_first():
    """Обрезка profile: строки с 'сильные стороны'/'достижения' убираются первыми."""
    from bot.memory.context_builder import _truncate_context

    profile_lines = [
        "=== ПРОФИЛЬ ===",
        "Имя: Маша",
        "Возраст: 28",
        "Сильные стороны: эмпатия, чуткость",
        "Достижения: повышение на работе",
        "Страхи: отказ, конфликт",
    ]
    sections = {
        "base_prompt": "Ты — Ева. " * 1200,
        "profile": "\n".join(profile_lines),
        "procedural": "Работает: рефлексия " * 100,
        "episodes": "Разговор про работу " * 200,
        "patterns": "Избегает конфликтов " * 100,
        "commitments": "Научиться говорить нет " * 50,
        "pause_context": "",
    }

    _truncate_context(sections, _SAMPLE_EPISODES, _SAMPLE_PATTERNS, _SAMPLE_GOAL, _SAMPLE_STEPS)

    assert "Сильные стороны" not in sections["profile"]
    assert "Достижения" not in sections["profile"]
    assert "Имя: Маша" in sections["profile"]


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_returning_user_pause_in_prompt(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """Вернувшийся юзер (пауза > 24ч): 'Пауза' в промпте и pause_context в filled_vars."""
    user = _ACTIVE_USER.copy()
    user["last_message_at"] = "2026-02-25 10:00:00"
    mock_db.get_user = AsyncMock(return_value=user)
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.return_value = "=== ПРОФИЛЬ ===\nИмя: Лена"
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗЕРКАЛО"

    from bot.memory.context_builder import build_context

    prompt, _, meta = await build_context(222, "Я всё провалила")

    assert "Пауза" in prompt
    assert "дн." in prompt
    assert "pause_context" in meta.filled_vars


@pytest.mark.asyncio
async def test_truncation_commitments_only_pending():
    """Обрезка приоритет 2: commitments обрезается до pending-шагов."""
    from bot.memory.context_builder import _truncate_context

    goal = {"id": 1, "title": "Цель"}
    steps = [
        {"title": "Шаг выполнен", "status": "completed", "deadline_at": None},
        {"title": "Шаг в работе", "status": "pending", "deadline_at": None},
    ]

    sections = {
        "base_prompt": "Ты — Ева. " * 1200,
        "profile": "Профиль " * 200,
        "procedural": "Процедурная " * 100,
        "episodes": "Эпизоды " * 200,
        "patterns": "Паттерны " * 100,
        "commitments": "=== ТЕКУЩАЯ ЦЕЛЬ ===\nЦель\n☑ Шаг выполнен\n☐ Шаг в работе",
        "pause_context": "",
    }

    truncated = _truncate_context(sections, _SAMPLE_EPISODES, _SAMPLE_PATTERNS, goal, steps)

    assert "commitments" in truncated
    assert "Шаг выполнен" not in sections["commitments"]
    assert "Шаг в работе" in sections["commitments"]


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_active_user_all_sections(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """Активный юзер с заполненными секциями: filled_vars содержит все ключи."""
    mock_db.get_user = AsyncMock(return_value=_ACTIVE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=_SAMPLE_PATTERNS)
    mock_db.get_active_goal = AsyncMock(return_value=_SAMPLE_GOAL.copy())
    mock_db.get_goal_steps = AsyncMock(return_value=_SAMPLE_STEPS)
    mock_prof.return_value = "=== ПРОФИЛЬ ===\nИмя: Маша\nВозраст: 28"
    mock_eps.return_value = _SAMPLE_EPISODES
    mock_proc.return_value = "=== ПРОЦЕДУРНАЯ ПАМЯТЬ ===\nРаботает: отражение слов"
    mock_bsp.return_value = "Ты — Ева. Тёплая подруга. ЗЕРКАЛО"

    from bot.memory.context_builder import build_context

    prompt, token_count, meta = await build_context(222, "Мне грустно")

    # Все секции заполнены (кроме pause_context — пауза < 60 мин)
    for section in ("base_prompt", "profile", "procedural", "episodes", "patterns", "commitments"):
        assert section in meta.filled_vars, f"Секция '{section}' отсутствует в filled_vars"


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_truncation_removes_pause_first(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """Контекст > 3800 токенов: was_truncated=True, pause_context в truncated_vars."""
    # Юзер с паузой > 60 мин
    user = _ACTIVE_USER.copy()
    user["last_message_at"] = "2026-01-01 10:00:00"  # давно
    mock_db.get_user = AsyncMock(return_value=user)
    mock_db.get_patterns = AsyncMock(return_value=_SAMPLE_PATTERNS)
    mock_db.get_active_goal = AsyncMock(return_value=_SAMPLE_GOAL.copy())
    mock_db.get_goal_steps = AsyncMock(return_value=_SAMPLE_STEPS)

    # Длинные тексты чтобы превысить бюджет
    mock_prof.return_value = "=== ПРОФИЛЬ ===\n" + "Важная информация. " * 300
    mock_eps.return_value = _SAMPLE_EPISODES
    mock_proc.return_value = "=== ПРОЦЕДУРНАЯ ПАМЯТЬ ===\n" + "Работает: рефлексия. " * 200
    mock_bsp.return_value = _LONG_BASE

    from bot.memory.context_builder import build_context

    prompt, token_count, meta = await build_context(222, "Привет")

    assert meta.was_truncated is True
    assert "pause_context" in meta.truncated_vars


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_safe_call_handles_error(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """get_profile_as_text бросает Exception -> build_context НЕ падает, fallback подставлен."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.side_effect = RuntimeError("DB connection lost")
    mock_prof.__name__ = "get_profile_as_text"  # _safe_call логирует fn.__name__
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    # Не должно упасть
    prompt, token_count, meta = await build_context(111, "Привет")

    # Fallback профиль подставлен
    assert "Новый пользователь" in prompt
    assert token_count > 0


@pytest.mark.asyncio
@patch("bot.memory.context_builder.database")
async def test_user_not_found_raises_valueerror(mock_db):
    """get_user вернул None -> ValueError."""
    mock_db.get_user = AsyncMock(return_value=None)

    from bot.memory.context_builder import build_context

    with pytest.raises(ValueError, match="not found"):
        await build_context(999, "Привет")


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_base_prompt_always_first(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """Результат начинается с base_prompt (для prompt caching)."""
    base = "Ты — Ева. Тёплая подруга. ЗНАКОМСТВО"
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.return_value = "=== ПРОФИЛЬ ===\nИмя: Маша"
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = base

    from bot.memory.context_builder import build_context

    prompt, _, _ = await build_context(111, "Привет")

    assert prompt.startswith(base)


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_context_meta_tokens_per_var(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """tokens_per_var содержит токены для всех заполненных секций."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.return_value = "=== ПРОФИЛЬ ===\nИмя: Маша"
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    _, _, meta = await build_context(111, "Привет")

    # Каждая заполненная переменная должна иметь запись в tokens_per_var
    for var_name in meta.filled_vars:
        assert var_name in meta.tokens_per_var, f"{var_name} отсутствует в tokens_per_var"
        assert meta.tokens_per_var[var_name] > 0, f"{var_name} имеет 0 токенов"


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_running_summary_in_prompt(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """running_summary непустой -> секция СОДЕРЖАНИЕ РАЗГОВОРА в промпте."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_db.get_running_summary = AsyncMock(
        return_value="ФАКТЫ: Маша, 28 лет.\nЭМОЦИИ: тревога."
    )
    mock_prof.return_value = ""
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    prompt, _, meta = await build_context(111, "Привет")

    assert "СОДЕРЖАНИЕ РАЗГОВОРА" in prompt
    assert "Маша, 28 лет" in prompt
    assert "running_summary" in meta.filled_vars


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_running_summary_empty_not_in_prompt(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """running_summary пустой -> секция НЕ в промпте."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_db.get_running_summary = AsyncMock(return_value="")
    mock_prof.return_value = ""
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    prompt, _, meta = await build_context(111, "Привет")

    assert "СОДЕРЖАНИЕ РАЗГОВОРА" not in prompt
    assert "running_summary" not in meta.filled_vars


@pytest.mark.asyncio
@patch("bot.memory.context_builder.build_system_prompt")
@patch("bot.memory.context_builder.get_procedural_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.find_relevant_episodes", new_callable=AsyncMock)
@patch("bot.memory.context_builder.get_profile_as_text", new_callable=AsyncMock)
@patch("bot.memory.context_builder.database")
async def test_empty_profile_fallback(
    mock_db, mock_prof, mock_eps, mock_proc, mock_bsp,
):
    """get_profile_as_text вернул '' -> 'Новый пользователь' в промпте."""
    mock_db.get_user = AsyncMock(return_value=_BASE_USER.copy())
    mock_db.get_patterns = AsyncMock(return_value=[])
    mock_db.get_active_goal = AsyncMock(return_value=None)
    mock_prof.return_value = ""
    mock_eps.return_value = []
    mock_proc.return_value = ""
    mock_bsp.return_value = "Ты — Ева. ЗНАКОМСТВО"

    from bot.memory.context_builder import build_context

    prompt, _, _ = await build_context(111, "Привет")

    assert "Новый пользователь" in prompt
