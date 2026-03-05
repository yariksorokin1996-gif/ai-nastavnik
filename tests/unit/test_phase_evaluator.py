"""
Тесты для bot/prompts/phase_evaluator.py
6 тестов: advance, stay, invalid JSON, LLM error, РИТМ (no call), user not found.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import patch

import pytest

from shared.llm_client import LLMError
from shared.models import PhaseEvaluation


_SAMPLE_MESSAGES = [
    {"role": "user", "content": "Привет, меня зовут Маша"},
    {"role": "assistant", "content": "Привет, Маша! Расскажи, что тебя беспокоит?"},
    {"role": "user", "content": "Мне тяжело с мамой общаться"},
]


# ---------------------------------------------------------------------------
# 1. test_advance_recommendation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.prompts.phase_evaluator.call_gpt")
@patch("bot.prompts.phase_evaluator.get_user")
async def test_advance_recommendation(mock_get_user, mock_call_gpt):
    """LLM рекомендует advance с высокой confidence."""
    mock_get_user.return_value = {"current_phase": "ЗНАКОМСТВО"}
    mock_call_gpt.return_value = json.dumps({
        "recommendation": "advance",
        "confidence": 0.85,
        "criteria_met": ["Знает имя", "Знает боль"],
    })

    from bot.prompts.phase_evaluator import evaluate_phase

    result = await evaluate_phase(123, messages=_SAMPLE_MESSAGES)

    assert isinstance(result, PhaseEvaluation)
    assert result.recommendation == "advance"
    assert result.confidence == 0.85
    assert len(result.criteria_met) == 2
    assert "Знает имя" in result.criteria_met
    mock_call_gpt.assert_called_once()


# ---------------------------------------------------------------------------
# 2. test_stay_low_confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.prompts.phase_evaluator.call_gpt")
@patch("bot.prompts.phase_evaluator.get_user")
async def test_stay_low_confidence(mock_get_user, mock_call_gpt):
    """LLM рекомендует stay с низкой confidence."""
    mock_get_user.return_value = {"current_phase": "ЗЕРКАЛО"}
    mock_call_gpt.return_value = json.dumps({
        "recommendation": "stay",
        "confidence": 0.3,
        "criteria_met": [],
    })

    from bot.prompts.phase_evaluator import evaluate_phase

    result = await evaluate_phase(123, messages=_SAMPLE_MESSAGES)

    assert result.recommendation == "stay"
    assert result.confidence == 0.3
    assert result.criteria_met == []


# ---------------------------------------------------------------------------
# 3. test_invalid_json_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.prompts.phase_evaluator.call_gpt")
@patch("bot.prompts.phase_evaluator.get_user")
async def test_invalid_json_fallback(mock_get_user, mock_call_gpt):
    """Невалидный JSON от LLM -> fallback (stay, 0.0)."""
    mock_get_user.return_value = {"current_phase": "ЗНАКОМСТВО"}
    mock_call_gpt.return_value = "not json at all"

    from bot.prompts.phase_evaluator import evaluate_phase

    result = await evaluate_phase(123, messages=_SAMPLE_MESSAGES)

    assert result.recommendation == "stay"
    assert result.confidence == 0.0
    assert result.criteria_met == []


# ---------------------------------------------------------------------------
# 4. test_llm_error_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.prompts.phase_evaluator.call_gpt")
@patch("bot.prompts.phase_evaluator.get_user")
async def test_llm_error_fallback(mock_get_user, mock_call_gpt):
    """LLMError от call_gpt -> fallback (stay, 0.0)."""
    mock_get_user.return_value = {"current_phase": "ЗНАКОМСТВО"}
    mock_call_gpt.side_effect = LLMError("timeout")

    from bot.prompts.phase_evaluator import evaluate_phase

    result = await evaluate_phase(123, messages=_SAMPLE_MESSAGES)

    assert result.recommendation == "stay"
    assert result.confidence == 0.0
    assert result.criteria_met == []


# ---------------------------------------------------------------------------
# 5. test_ritm_phase_no_llm_call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.prompts.phase_evaluator.call_gpt")
@patch("bot.prompts.phase_evaluator.get_user")
async def test_ritm_phase_no_llm_call(mock_get_user, mock_call_gpt):
    """Фаза РИТМ -- финальная, LLM НЕ вызывается."""
    mock_get_user.return_value = {"current_phase": "РИТМ"}

    from bot.prompts.phase_evaluator import evaluate_phase

    result = await evaluate_phase(123, messages=_SAMPLE_MESSAGES)

    assert result.recommendation == "stay"
    assert result.confidence == 0.0
    mock_call_gpt.assert_not_called()


# ---------------------------------------------------------------------------
# 6. test_user_not_found_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.prompts.phase_evaluator.call_gpt")
@patch("bot.prompts.phase_evaluator.get_user")
async def test_user_not_found_fallback(mock_get_user, mock_call_gpt):
    """Пользователь не найден -> fallback (stay, 0.0)."""
    mock_get_user.return_value = None

    from bot.prompts.phase_evaluator import evaluate_phase

    result = await evaluate_phase(123, messages=_SAMPLE_MESSAGES)

    assert result.recommendation == "stay"
    assert result.confidence == 0.0
    assert result.criteria_met == []
    mock_call_gpt.assert_not_called()
