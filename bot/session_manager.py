"""Конвейер обработки сообщений -- 14 шагов от получения до ответа Евы.

Публичный API:
    process_message(telegram_id, message_id, text, user_name, is_voice) -> str | None

Гарантии:
- Идемпотентность по message_id (None если уже обработано)
- Мьютекс на пользователя (одновременно один запрос)
- НИКОГДА не бросает исключение вызывающему -- всегда FALLBACK или кризисный ответ
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

from bot.analytics.alerter import alerter
from bot.memory.context_builder import build_context
from bot.memory import database
from bot.memory.database import (
    add_emotion,
    add_message,
    add_pending_fact,
    add_phase_transition,
    create_user,
    get_recent_messages,
    get_user,
    is_message_processed,
    mark_message_processed,
    update_user,
)
from bot.memory.full_memory_update import update_single_user
from bot.prompts.phase_evaluator import evaluate_phase
from shared.config import (
    CLAUDE_TIMEOUT,
    DIALOG_GPT_MODEL,
    DIALOG_PROVIDER,
    FALLBACK_RESPONSE,
    RATE_LIMIT_PER_MINUTE,
)
from shared.llm_client import LLMError, call_claude, call_gpt
from shared.safety import (
    CRISIS_INSTRUCTION_LEVEL2,
    CRISIS_RESPONSE_LEVEL3,
    detect_crisis,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Модуль-уровневое состояние
# ---------------------------------------------------------------------------

_user_locks: dict[int, asyncio.Lock] = {}
_rate_counters: dict[int, list[float]] = {}  # telegram_id -> [timestamps]
_consecutive_errors: dict[int, int] = {}

# ---------------------------------------------------------------------------
# Фазовая система
# ---------------------------------------------------------------------------

PHASE_ORDER: list[str] = [
    "ЗНАКОМСТВО",
    "ЗЕРКАЛО",
    "НАСТРОЙКА",
    "ПОРТРЕТ",
    "ЦЕЛЬ",
    "РИТМ",
]

PHASE_THRESHOLDS: dict[str, int | None] = {
    "ЗНАКОМСТВО": 5,
    "ЗЕРКАЛО": 10,
    "НАСТРОЙКА": 18,
    "ПОРТРЕТ": 25,
    "ЦЕЛЬ": 35,
    "РИТМ": None,  # финальная фаза
}

# ---------------------------------------------------------------------------
# Словарь эмоций для мини-обновления памяти
# ---------------------------------------------------------------------------

EMOTION_KEYWORDS: dict[str, list[str]] = {
    "злость": ["бешу", "злюсь", "бесит", "взбесил", "раздражает"],
    "грусть": ["грустно", "тоскливо", "плачу", "слёзы", "слезы"],
    "радость": ["радость", "счастлива", "кайф", "ура", "круто"],
    "тревога": ["волнуюсь", "страшно", "боюсь", "паника", "тревожно"],
    "усталость": ["устала", "устал", "выгорела", "выгорел", "сил нет", "замучена"],
}

# Стоп-лист имён для мини-обновления
_NAME_STOP_LIST: set[str] = {
    "Бог", "Господь", "Инстаграм", "Телеграм",
    "Россия", "Москва", "Питер", "Петербург", "Ютуб",
}

# Разнообразные fallback-ответы (UX #5)
_FALLBACK_VARIANTS: list[str] = [
    FALLBACK_RESPONSE,
    "Секунду, собираюсь с мыслями...",
    "Прости, задумалась. Попробуй написать ещё раз?",
]

_FALLBACK_PERSISTENT = "Кажется, у меня что-то сломалось. Попробуй чуть позже, ладно? 💛"


# ===========================================================================
# Публичный API
# ===========================================================================


async def process_message(
    telegram_id: int,
    message_id: int,
    text: str,
    user_name: str | None,
    is_voice: bool = False,
) -> str | None:
    """Главный конвейер обработки сообщения.

    Returns:
        Строка с ответом Евы, или None если сообщение уже обработано (идемпотентность).
    """
    # --- Step 1: Entry ---
    start_time = time.monotonic()

    try:
        # --- Step 2: Idempotency ---
        if await is_message_processed(message_id):
            return None

        # --- Step 3: Mutex (per-user lock) ---
        async with _get_user_lock(telegram_id):
            return await _process_under_lock(
                telegram_id=telegram_id,
                message_id=message_id,
                text=text,
                user_name=user_name,
                is_voice=is_voice,
                start_time=start_time,
            )
    except Exception:
        logger.exception("ALERT: unhandled_error user %s", telegram_id)
        return _get_fallback_response(telegram_id)


async def _process_under_lock(
    *,
    telegram_id: int,
    message_id: int,
    text: str,
    user_name: str | None,
    is_voice: bool,
    start_time: float,
) -> str | None:
    """Обработка внутри мьютекса -- шаги 4-14."""

    # --- Step 4: Get/create user + calculate pause ---
    user = await get_user(telegram_id)
    if not user:
        user = await create_user(telegram_id, name=user_name)

    # pause_minutes используется build_context (читает last_message_at из БД)

    # --- Step 5: Voice already transcribed in handlers -- skip ---

    # --- Step 6: Crisis detection ---
    crisis = await detect_crisis(text)

    if crisis.level == 3:
        await add_message(
            telegram_id, "user", text,
            source="user", is_voice=int(is_voice),
        )
        await add_message(
            telegram_id, "assistant", CRISIS_RESPONSE_LEVEL3,
            source="crisis",
        )
        await mark_message_processed(message_id, telegram_id)
        logger.error(
            "ALERT: crisis_level_3 user %s trigger=%s",
            telegram_id, crisis.trigger,
        )
        await alerter.check(telegram_id, "crisis_level_3", value=crisis.trigger)
        return CRISIS_RESPONSE_LEVEL3

    # --- Step 7: Rate limit ---
    if not _check_rate_limit(telegram_id):
        return "Ой, ты так быстро пишешь! Дай мне секунду собраться с мыслями 😅"

    # --- Step 8: Save message + mark processed ---
    await add_message(
        telegram_id, "user", text,
        source="user", is_voice=int(is_voice),
    )
    await mark_message_processed(message_id, telegram_id)

    # --- Step 9: Build context ---
    try:
        system_prompt, token_count, meta = await build_context(telegram_id, text)
    except Exception:
        logger.exception("build_context failed for %s", telegram_id)
        await alerter.check(telegram_id, "consecutive_empty_context")
        return _get_fallback_response(telegram_id)

    # --- Step 10: Call Claude ---

    # Если crisis level 2, добавляем инструкцию в системный промпт
    if crisis.level == 2:
        system_prompt += f"\n\n{CRISIS_INSTRUCTION_LEVEL2}"

    # UX #10: Post-crisis контекст
    recent = await get_recent_messages(telegram_id, limit=12)
    if _was_recent_crisis(recent):
        system_prompt += (
            "\n\nПользовательница недавно была в кризисном состоянии. "
            "Мягко спроси как она сейчас, не давя."
        )

    messages_for_claude = []
    prev_time = None
    pending_pause = ""
    for m in recent:
        curr_time = m.get("created_at")
        if prev_time and curr_time:
            gap = (datetime.fromisoformat(curr_time) - datetime.fromisoformat(prev_time)).total_seconds()
            if gap > 1800:  # 30 мин
                pause_text = _format_pause(gap)
                pending_pause = f"[{pause_text}]\n"
        content = m["content"]
        if pending_pause and m["role"] == "user":
            content = pending_pause + content
            pending_pause = ""
        messages_for_claude.append({"role": m["role"], "content": content})
        prev_time = curr_time

    try:
        if DIALOG_PROVIDER == "openai":
            response = await call_gpt(
                messages=messages_for_claude,
                system=system_prompt,
                max_tokens=400,
                model_override=DIALOG_GPT_MODEL,
            )
        else:
            response = await call_claude(
                messages=messages_for_claude,
                system=system_prompt,
                max_tokens=400,
                timeout=CLAUDE_TIMEOUT,
            )
        _consecutive_errors.pop(telegram_id, None)  # сброс при успехе
        alerter.reset(telegram_id, "consecutive_errors")
        alerter.reset(telegram_id, "consecutive_empty_context")
    except LLMError as e:
        logger.error("LLM call failed for %s: %s", telegram_id, e)
        _consecutive_errors[telegram_id] = _consecutive_errors.get(telegram_id, 0) + 1
        await alerter.check(telegram_id, "consecutive_errors")
        if _consecutive_errors.get(telegram_id, 0) >= 3:
            logger.error(
                "ALERT: consecutive_errors user %s count=%d",
                telegram_id, _consecutive_errors[telegram_id],
            )
        return _get_fallback_response(telegram_id)

    # --- Step 11: Save response + truncate if needed ---
    response = _truncate_response(response, max_len=4000)
    latency_ms = int((time.monotonic() - start_time) * 1000)
    await add_message(
        telegram_id, "assistant", response,
        source="user", response_latency_ms=latency_ms,
    )
    if latency_ms > 25_000:
        logger.error(
            "ALERT: latency_critical_ms user %s latency=%d",
            telegram_id, latency_ms,
        )
        await alerter.check(telegram_id, "latency_critical_ms", value=latency_ms)

    # --- Step 11b: mark_daily_responded если юзер ответил на daily message ---
    try:
        daily = await database.get_unresponded_daily(telegram_id)
        if daily and daily.get("sent_at"):
            sent_dt = datetime.fromisoformat(daily["sent_at"])
            if sent_dt.tzinfo is None:
                sent_dt = sent_dt.replace(tzinfo=timezone.utc)
            delay = int(
                (datetime.now(timezone.utc) - sent_dt).total_seconds() / 60
            )
            await database.mark_daily_responded(daily["id"], delay)
    except Exception:
        logger.warning(
            "mark_daily_responded failed for %s", telegram_id, exc_info=True,
        )

    # --- Step 12: ASYNC mini memory update (fire-and-forget) ---
    asyncio.create_task(_mini_memory_update(telegram_id, text, response))

    # --- Step 13: ASYNC phase check + memory update (every 10 messages) ---
    messages_total = user.get("messages_total", 0) + 1
    if messages_total % 10 == 0:
        asyncio.create_task(_check_phase_transition(telegram_id, messages_total))
        asyncio.create_task(_trigger_memory_update(telegram_id))

    # --- Step 14: Update counters ---
    pause_minutes = _calc_pause_minutes(user.get("last_message_at"))
    if pause_minutes and pause_minutes >= 30:
        needs_update = 1  # Пауза > 30 мин — триггерим обновление памяти
    elif messages_total % 10 == 0:
        needs_update = 1
    else:
        needs_update = 0
    await update_user(
        telegram_id,
        last_message_at=_now(),
        messages_total=messages_total,
        needs_full_update=needs_update,
    )

    return response


# ===========================================================================
# Вспомогательные функции
# ===========================================================================


def _get_user_lock(telegram_id: int) -> asyncio.Lock:
    """Ленивое создание per-user мьютекса (атомарно через setdefault)."""
    return _user_locks.setdefault(telegram_id, asyncio.Lock())


def _check_rate_limit(telegram_id: int) -> bool:
    """Проверяет, не превышен ли rate limit. True = можно продолжать."""
    now = time.monotonic()
    window = 60.0

    timestamps = _rate_counters.get(telegram_id, [])
    # Убираем записи старше 60 секунд
    timestamps = [t for t in timestamps if now - t < window]
    _rate_counters[telegram_id] = timestamps

    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        return False

    timestamps.append(now)
    return True


def _calc_pause_minutes(last_message_at: str | None) -> int | None:
    """Вычисляет минуты паузы с последнего сообщения. None если нет данных."""
    if not last_message_at:
        return None
    try:
        last_dt = datetime.fromisoformat(last_message_at)
        # Если нет tzinfo, считаем UTC
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        delta = now_dt - last_dt
        return max(0, int(delta.total_seconds() / 60))
    except (ValueError, TypeError):
        return None


def _now() -> str:
    """Текущее время в ISO формате (UTC)."""
    return datetime.now(timezone.utc).isoformat()


def _truncate_response(text: str, max_len: int = 4000) -> str:
    """Обрезает ответ до max_len символов с учётом пунктуации (UX #6)."""
    if len(text) <= max_len:
        return text

    truncated = text[:max_len]
    # Ищем последний знак препинания для естественного обрыва
    last_punct = -1
    for punct in ".!?":
        idx = truncated.rfind(punct)
        if idx > last_punct:
            last_punct = idx

    if last_punct > 0:
        return truncated[: last_punct + 1]

    return truncated + "..."


def _get_fallback_response(telegram_id: int) -> str:
    """Разнообразные fallback-ответы (UX #5)."""
    error_count = _consecutive_errors.get(telegram_id, 0)
    if error_count >= 3:
        return _FALLBACK_PERSISTENT
    # Ротация по error_count
    idx = error_count % len(_FALLBACK_VARIANTS)
    return _FALLBACK_VARIANTS[idx]


def _was_recent_crisis(messages: list[dict]) -> bool:
    """Проверяет, был ли недавний кризисный ответ Level 3."""
    prefix = CRISIS_RESPONSE_LEVEL3[:30]
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("content", "").startswith(prefix):
            return True
    return False


def _format_pause(seconds: float) -> str:
    """Форматирует паузу в человекочитаемый вид."""
    days = int(seconds // 86400)
    if days >= 1:
        return f"Пауза {days} дн"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"Пауза {hours} ч {mins} мин" if hours else f"Пауза {mins} мин"


def _get_next_phase(current: str) -> str | None:
    """Следующая фаза из PHASE_ORDER или None если уже РИТМ."""
    try:
        idx = PHASE_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 < len(PHASE_ORDER):
        return PHASE_ORDER[idx + 1]
    return None


# ===========================================================================
# Фоновые задачи (fire-and-forget через create_task)
# ===========================================================================


async def _mini_memory_update(
    telegram_id: int,
    user_text: str,
    bot_response: str,
) -> None:
    """Мини-обновление памяти на основе regex (без LLM). Запускается в фоне."""
    try:
        text_lower = user_text.lower()

        # 1. Имена: «мой/моя/моих/моему...» + Имя
        name_matches = re.findall(r"мо[йяиюей]\s+([А-ЯЁ][а-яё]{2,})", user_text)
        for name in name_matches:
            if name not in _NAME_STOP_LIST:
                await add_pending_fact(
                    telegram_id, "person", name, confidence="medium",
                )

        # 2. Обязательства
        commitment_pattern = (
            r"(завтра|на этой неделе|обещаю|попробую|планирую|решила)\s+(.+?)(?:\.|$)"
        )
        commitment_matches = re.findall(commitment_pattern, text_lower)
        for _trigger, commitment_text in commitment_matches:
            await add_pending_fact(
                telegram_id, "commitment", commitment_text.strip(),
                confidence="medium",
            )

        # 3. Возраст
        age_match = re.search(r"мне\s+(\d{2})\s+(год|лет|года)", text_lower)
        if age_match:
            age = int(age_match.group(1))
            if 14 <= age <= 100:
                await add_pending_fact(
                    telegram_id, "age", str(age), confidence="high",
                )

        # 4. Эмоции
        for emotion, keywords in EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    await add_emotion(telegram_id, emotion)
                    break  # одна эмоция за категорию

    except Exception:
        logger.warning(
            "mini_memory_update failed for user %s", telegram_id, exc_info=True,
        )


async def _trigger_memory_update(telegram_id: int) -> None:
    """Запускает полное обновление памяти (fire-and-forget, каждые 10 msg)."""
    try:
        await update_user(telegram_id, needs_full_update=0)
        await update_single_user(telegram_id)
    except Exception:
        logger.warning(
            "trigger_memory_update failed for user %s",
            telegram_id, exc_info=True,
        )


async def _check_phase_transition(telegram_id: int, messages_total: int) -> None:
    """Проверка фазового перехода через LLM. Запускается в фоне каждые 5 сообщений."""
    try:
        user = await get_user(telegram_id)
        if not user:
            return

        current_phase = user.get("current_phase", "ЗНАКОМСТВО")

        # Проверяем порог для текущей фазы
        threshold = PHASE_THRESHOLDS.get(current_phase)
        if threshold is None:
            # Финальная фаза (РИТМ) -- переходить некуда
            return
        if messages_total < threshold:
            # Ещё рано для перехода
            return

        # Получаем последние 10 сообщений для оценки
        recent = await get_recent_messages(telegram_id, limit=10)
        evaluation = await evaluate_phase(telegram_id, recent)

        force_advance = messages_total >= threshold * 3

        if force_advance or (evaluation.recommendation == "advance" and evaluation.confidence >= 0.7):
            next_phase = _get_next_phase(current_phase)
            if next_phase:
                await update_user(telegram_id, current_phase=next_phase)
                await add_phase_transition(
                    telegram_id,
                    from_phase=current_phase,
                    to_phase=next_phase,
                    reason=", ".join(evaluation.criteria_met),
                    messages_count=messages_total,
                )
                if force_advance:
                    logger.warning(
                        "FORCE phase advance user %s: %s -> %s (messages=%d, threshold=%d)",
                        telegram_id, current_phase, next_phase, messages_total, threshold,
                    )
                else:
                    logger.info(
                        "Phase transition user %s: %s -> %s (confidence=%.2f)",
                        telegram_id, current_phase, next_phase, evaluation.confidence,
                    )
        else:
            logger.info(
                "Phase stay user %s: phase=%s confidence=%.2f criteria=%s",
                telegram_id, current_phase, evaluation.confidence, evaluation.criteria_met,
            )

    except Exception:
        logger.warning(
            "phase_transition check failed for user %s",
            telegram_id, exc_info=True,
        )
