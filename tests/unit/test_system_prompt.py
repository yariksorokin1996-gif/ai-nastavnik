"""Тесты для bot/prompts/system_prompt.py и bot/prompts/memory_prompts.py. 13 тестов."""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bot.prompts.memory_prompts import (
    PHASE_EVALUATION_PROMPT,
    PHASE_TRANSITION_CRITERIA,
    PROFILE_UPDATE_PROMPT,
)
from bot.prompts.system_prompt import build_system_prompt


# ---------------------------------------------------------------------------
# build_system_prompt — все 6 фаз
# ---------------------------------------------------------------------------


def test_build_system_prompt_znakomstvo():
    """Фаза ЗНАКОМСТВО присутствует в промпте."""
    result = build_system_prompt("ЗНАКОМСТВО")
    assert "ЗНАКОМСТВО" in result


def test_build_system_prompt_zerkalo():
    """Фаза ЗЕРКАЛО присутствует в промпте."""
    result = build_system_prompt("ЗЕРКАЛО")
    assert "ЗЕРКАЛО" in result


def test_build_system_prompt_nastroika():
    """Фаза НАСТРОЙКА присутствует в промпте."""
    result = build_system_prompt("НАСТРОЙКА")
    assert "НАСТРОЙКА" in result


def test_build_system_prompt_portret():
    """Фаза ПОРТРЕТ присутствует в промпте."""
    result = build_system_prompt("ПОРТРЕТ")
    assert "ПОРТРЕТ" in result


def test_build_system_prompt_tsel():
    """Фаза ЦЕЛЬ присутствует в промпте."""
    result = build_system_prompt("ЦЕЛЬ")
    assert "ЦЕЛЬ" in result


def test_build_system_prompt_ritm():
    """Фаза РИТМ присутствует в промпте."""
    result = build_system_prompt("РИТМ")
    assert "РИТМ" in result


# ---------------------------------------------------------------------------
# Защита роли: нет «Алекс», есть «Ева»
# ---------------------------------------------------------------------------


def test_build_system_prompt_no_alex():
    """Промпт НЕ содержит 'Алекс' / 'алекс' / 'Alex' ни в одной фазе."""
    for phase in ("ЗНАКОМСТВО", "ЗЕРКАЛО", "НАСТРОЙКА", "ПОРТРЕТ", "ЦЕЛЬ", "РИТМ"):
        result = build_system_prompt(phase)
        lower = result.lower()
        assert "алекс" not in lower, f"Фаза {phase}: найдено 'алекс'"
        assert "alex" not in lower, f"Фаза {phase}: найдено 'alex'"


def test_build_system_prompt_has_eva():
    """Промпт содержит 'Ева' в базовой части (общая для всех фаз)."""
    result = build_system_prompt("ЗНАКОМСТВО")
    assert "Ева" in result


# ---------------------------------------------------------------------------
# Fallback при неизвестной фазе
# ---------------------------------------------------------------------------


def test_build_system_prompt_unknown_phase_fallback():
    """Неизвестная фаза -> fallback на ЗНАКОМСТВО."""
    result = build_system_prompt("НЕИЗВЕСТНАЯ")
    assert "ЗНАКОМСТВО" in result


# ---------------------------------------------------------------------------
# Синхронность
# ---------------------------------------------------------------------------


def test_build_system_prompt_is_sync():
    """build_system_prompt — обычная функция, НЕ корутина."""
    assert not inspect.iscoroutinefunction(build_system_prompt)


# ---------------------------------------------------------------------------
# memory_prompts: format-строки и ключи
# ---------------------------------------------------------------------------


def test_profile_update_prompt_format():
    """PROFILE_UPDATE_PROMPT.format() без KeyError при всех ожидаемых ключах."""
    result = PROFILE_UPDATE_PROMPT.format(
        current_profile="x",
        new_messages="x",
        episode_summary="x",
        pending_facts="x",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_phase_evaluation_prompt_format():
    """PHASE_EVALUATION_PROMPT.format() без KeyError при всех ожидаемых ключах."""
    result = PHASE_EVALUATION_PROMPT.format(
        current_phase="x",
        transition_criteria="x",
        recent_messages="x",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_phase_transition_criteria_all_phases():
    """PHASE_TRANSITION_CRITERIA содержит ключи для всех 6 фаз."""
    expected = {"ЗНАКОМСТВО", "ЗЕРКАЛО", "НАСТРОЙКА", "ПОРТРЕТ", "ЦЕЛЬ", "РИТМ"}
    assert set(PHASE_TRANSITION_CRITERIA.keys()) == expected
