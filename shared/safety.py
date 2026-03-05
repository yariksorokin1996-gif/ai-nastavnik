"""Модуль кризисного детектирования -- 3 уровня с LLM-верификацией.

Level 3 -- суицид -> шаблон с телефонами, БЕЗ Claude, БЕЗ LLM-verify
Level 2 -- насилие/самоповреждение -> LLM-верификация false positives
Level 1 -- мягкие сигналы -> LLM-верификация false positives
Level 0 -- норма
"""
from __future__ import annotations

import json
import logging

from shared.llm_client import call_gpt, LLMError
from shared.models import CrisisResult
from bot.prompts.memory_prompts import CRISIS_VERIFICATION_PROMPT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Шаблоны ответов
# ---------------------------------------------------------------------------

CRISIS_RESPONSE_LEVEL3 = (
    "Я слышу, что тебе сейчас очень тяжело. "
    "Это важнее, чем наш разговор.\n\n"
    "Пожалуйста, позвони сейчас:\n"
    "8-800-2000-122 (бесплатно, круглосуточно)\n\n"
    "Я здесь. Но прямо сейчас тебе нужен живой человек. \U0001f49b"
)

CRISIS_INSTRUCTION_LEVEL2 = (
    "\u26a0\ufe0f ВАЖНО: возможная ситуация насилия или самоповреждения.\n"
    "1. Спроси: \u00abТы сейчас в безопасности?\u00bb\n"
    "2. Если нет \u2192 дай контакт: 8-800-7000-600 "
    "(центр помощи, бесплатно, 24/7), экстренная помощь 112.\n"
    "3. Не пытайся \u00abрешить\u00bb ситуацию. Будь рядом."
)

# ---------------------------------------------------------------------------
# Словари ключевых слов по уровням
# ---------------------------------------------------------------------------

_LEVEL3_KEYWORDS: list[str] = [
    "суицид", "суицида", "суициде",
    "убить себя", "убью себя", "хочу умереть", "хочу умер",
    "не хочу жить", "нет смысла жить", "лучше бы меня не было",
    "покончить с собой", "покончу с собой",
    "вскрыть вены", "вскрою вены",
    "таблетки выпить все", "передозировка",
    "прыгнуть", "повеситься",
    "самоповреждение", "режу себя",
]

_LEVEL2_KEYWORDS: list[str] = [
    # domestic violence
    "бьёт меня", "бьет меня", "ударил меня", "ударила меня",
    "душит меня", "душил меня",
    "угрожает убить", "угрожает мне",
    "боюсь его", "боюсь её", "боюсь мужа",
    "поднимает руку", "избивает",
    # addiction
    "не могу бросить пить", "алкоголизм", "спиваюсь",
    "наркотики", "наркозависимость", "сорвалась", "сорвался",
    "передоз",
    # eating disorder
    "булимия", "анорексия",
    "вызываю рвоту", "не ем", "не могу есть",
    "боюсь еды", "ненавижу своё тело",
    # postpartum
    "ненавижу ребёнка", "ненавижу ребенка",
    "жалею что родила",
    "не чувствую связи с ребёнком", "не чувствую связи с ребенком",
    "не люблю своего ребёнка", "не люблю своего ребенка",
    "хочу бросить ребёнка", "хочу бросить ребенка",
]

_LEVEL1_KEYWORDS: list[str] = [
    "всё бесполезно", "все бесполезно",
    "ничего не изменится", "никогда не изменится",
    "я устала от жизни", "я устал от жизни",
    "зачем всё это", "зачем все это",
    "нет сил", "нет больше сил",
    "хочу исчезнуть", "хочу пропасть",
]


# ---------------------------------------------------------------------------
# LLM-верификация (false positive check)
# ---------------------------------------------------------------------------

async def _verify_crisis(text: str, trigger: str) -> bool:
    """Проверяет через GPT-4o-mini, реальный ли кризис.

    Returns True если кризис реальный (или при любой ошибке -- conservative).
    """
    prompt = CRISIS_VERIFICATION_PROMPT.format(text=text, trigger=trigger)
    try:
        raw = await call_gpt(
            messages=[{"role": "user", "content": prompt}],
            timeout=10,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        data = json.loads(raw)
        result = bool(data["is_real_crisis"])
        logger.warning(
            "Crisis verification: trigger=%r is_real=%s reason=%s",
            trigger,
            result,
            data.get("reason", "?"),
        )
        return result
    except (LLMError, json.JSONDecodeError, KeyError) as exc:
        logger.warning(
            "Crisis verification failed (conservative=True): %s: %s",
            type(exc).__name__,
            exc,
        )
        return True


# ---------------------------------------------------------------------------
# Основная функция детектирования
# ---------------------------------------------------------------------------

async def detect_crisis(text: str) -> CrisisResult:
    """Определяет уровень кризиса в сообщении.

    Returns CrisisResult с level 0-3.
    Level 3 возвращается мгновенно (без LLM).
    Level 1-2 проходят LLM-верификацию на false positive.
    """
    text_lower = text.lower()

    # Level 3 -- суицид: мгновенный ответ, без LLM
    for kw in _LEVEL3_KEYWORDS:
        if kw in text_lower:
            return CrisisResult(level=3, trigger=kw, is_verified=True)

    # Level 2 -- насилие/самоповреждение: LLM-верификация
    for kw in _LEVEL2_KEYWORDS:
        if kw in text_lower:
            is_real = await _verify_crisis(text, kw)
            if is_real:
                return CrisisResult(level=2, trigger=kw, is_verified=True)
            return CrisisResult(level=0, trigger=None, is_verified=True)

    # Level 1 -- мягкие сигналы: LLM-верификация
    for kw in _LEVEL1_KEYWORDS:
        if kw in text_lower:
            is_real = await _verify_crisis(text, kw)
            if is_real:
                return CrisisResult(level=1, trigger=kw, is_verified=True)
            return CrisisResult(level=0, trigger=None, is_verified=True)

    # Level 0 -- норма
    return CrisisResult(level=0, trigger=None, is_verified=True)
