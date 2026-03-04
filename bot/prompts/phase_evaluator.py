"""Оценка готовности пользователя к переходу на следующую фазу.

Контракт:
  Вход: telegram_id (int), messages (list[dict])
  Выход: PhaseEvaluation(recommendation, confidence, criteria_met)
  Ошибки: любая -> _SAFE_FALLBACK (stay, 0.0, [])
"""

import json
import logging

from pydantic import ValidationError

from bot.memory.database import get_user
from bot.prompts.memory_prompts import (
    PHASE_EVALUATION_PROMPT,
    PHASE_TRANSITION_CRITERIA,
)
from shared.llm_client import LLMError, call_gpt
from shared.models import PhaseEvaluation

logger = logging.getLogger(__name__)

_SAFE_FALLBACK = PhaseEvaluation(
    recommendation="stay",
    confidence=0.0,
    criteria_met=[],
)


def _format_messages(messages: list[dict]) -> str:
    """Превращает list[dict] в читаемую строку для промпта."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        label = "Пользователь" if role == "user" else "Ева"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


async def evaluate_phase(
    telegram_id: int,
    messages: list[dict],
) -> PhaseEvaluation:
    """Оценивает готовность к переходу на следующую фазу.

    Args:
        telegram_id: ID пользователя для получения current_phase из БД.
        messages: Последние 10 сообщений [{"role": ..., "content": ...}].

    Returns:
        PhaseEvaluation с рекомендацией advance/stay.
    """
    # 1. Получить текущую фазу
    try:
        user = await get_user(telegram_id)
    except (TypeError, KeyError) as exc:
        logger.warning(
            "evaluate_phase fallback: get_user failed telegram_id=%d err=%s",
            telegram_id,
            exc,
        )
        return _SAFE_FALLBACK

    if user is None:
        logger.warning(
            "evaluate_phase fallback: user not found telegram_id=%d",
            telegram_id,
        )
        return _SAFE_FALLBACK

    current_phase: str = user["current_phase"]

    # 2. Финальная фаза -- переход невозможен
    if current_phase == "РИТМ":
        return PhaseEvaluation(
            recommendation="stay",
            confidence=0.0,
            criteria_met=[],
        )

    # 3. Критерии перехода
    criteria = PHASE_TRANSITION_CRITERIA.get(current_phase)
    if criteria is None:
        logger.warning(
            "evaluate_phase fallback: unknown phase=%s telegram_id=%d",
            current_phase,
            telegram_id,
        )
        return _SAFE_FALLBACK

    # 4. Форматирование сообщений
    formatted_messages = _format_messages(messages)

    # 5. Промпт
    prompt = PHASE_EVALUATION_PROMPT.format(
        current_phase=current_phase,
        transition_criteria=criteria,
        recent_messages=formatted_messages,
    )

    # 6-7. LLM-вызов + парсинг
    try:
        response = await call_gpt(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        data = json.loads(response)
        result = PhaseEvaluation(**data)
    except (json.JSONDecodeError, LLMError, TypeError, KeyError) as exc:
        logger.warning(
            "evaluate_phase fallback: llm/parse error telegram_id=%d err=%s",
            telegram_id,
            exc,
        )
        return _SAFE_FALLBACK
    except ValidationError as exc:
        logger.warning(
            "evaluate_phase fallback: validation error telegram_id=%d err=%s",
            telegram_id,
            exc,
        )
        return _SAFE_FALLBACK

    # 8. Успех
    logger.info(
        "evaluate_phase telegram_id=%d phase=%s recommendation=%s confidence=%.2f",
        telegram_id,
        current_phase,
        result.recommendation,
        result.confidence,
    )
    return result
