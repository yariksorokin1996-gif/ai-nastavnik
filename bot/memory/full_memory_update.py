"""
Полное обновление памяти (APScheduler job, каждые 5 минут).

Контракт:
    Вход: (нет аргументов для run_full_memory_update, telegram_id для update_single_user)
    Выход: list[FullUpdateResult] | FullUpdateResult
    Ошибки: не бросает наружу, ловит и записывает в result.error

5 шагов на пользователя:
    1. Загрузить сообщения с последнего обновления
    2. Создать конспект эпизода (GPT-4o-mini через episode_manager)
    3. Обновить семантический профиль (GPT-4o-mini)
    4. Обновить процедурную память
    5. Финализация (clear pending_facts, update user flags)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from shared.llm_client import LLMError, call_gpt
from shared.models import FullUpdateResult, ProfileDiff
from bot.memory import database
from bot.memory import profile_manager
from bot.memory import episode_manager
from bot.memory import procedural_memory
from bot.prompts.memory_prompts import (
    PROFILE_UPDATE_PROMPT,
    RUNNING_SUMMARY_COMPRESS_PROMPT,
    RUNNING_SUMMARY_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-user lock (не запускать два обновления для одного юзера параллельно)
# ---------------------------------------------------------------------------

_update_locks: dict[int, asyncio.Lock] = {}


def _get_update_lock(tid: int) -> asyncio.Lock:
    """Ленивое создание per-user мьютекса для full_memory_update."""
    return _update_locks.setdefault(tid, asyncio.Lock())


# ---------------------------------------------------------------------------
# Счётчик ошибок (in-memory, сбрасывается при перезапуске)
# ---------------------------------------------------------------------------

_error_counts: dict[int, int] = {}


def _increment_error(tid: int) -> int:
    """Инкрементирует счётчик ошибок, возвращает новое значение."""
    _error_counts[tid] = _error_counts.get(tid, 0) + 1
    return _error_counts[tid]


def _reset_error(tid: int) -> None:
    """Сбрасывает счётчик ошибок для пользователя."""
    _error_counts.pop(tid, None)


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _now() -> str:
    """UTC datetime строкой, совместимо с SQLite."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _format_messages(messages: list[dict], limit: int = 20) -> str:
    """Форматирует сообщения для промпта running summary."""
    return "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[-limit:]
    )


async def _update_running_summary(old_summary: str, messages: list[dict]) -> str:
    """Обновляет running summary через GPT-4o-mini. Сжимает если > 400 слов."""
    prompt = RUNNING_SUMMARY_PROMPT.format(
        current_summary=old_summary or "(пусто)",
        new_messages=_format_messages(messages),
    )
    new_summary = await call_gpt(
        messages=[{"role": "user", "content": prompt}],
        timeout=15,
    )
    if len(new_summary.split()) > 400:
        compress_prompt = RUNNING_SUMMARY_COMPRESS_PROMPT.format(summary=new_summary)
        new_summary = await call_gpt(
            messages=[{"role": "user", "content": compress_prompt}],
            timeout=15,
        )
        logger.info("Running summary compressed for shorter version")
    return new_summary


def _format_facts(facts: list[dict] | None) -> str:
    """Форматирует pending_facts для промпта."""
    if not facts:
        return "Нет новых фактов"
    return "\n".join(
        f"- [{f.get('fact_type', '?')}] {f.get('content', '?')} "
        f"(уверенность: {f.get('confidence', '?')})"
        for f in facts
    )


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


async def run_full_memory_update() -> list[FullUpdateResult]:
    """APScheduler entry point. Обрабатывает всех пользователей с needs_full_update=1.

    Возвращает список результатов (один на пользователя).
    """
    user_ids = await database.get_users_needing_update()
    if not user_ids:
        return []

    results: list[FullUpdateResult] = []

    for tid in user_ids:
        try:
            result = await update_single_user(tid)
            if result.error:
                count = _increment_error(tid)
                logger.warning(
                    "Full update failed for user %s: %s", tid, result.error
                )
                if count >= 3:
                    logger.error(
                        "3 consecutive update errors for user %s", tid
                    )
            else:
                _reset_error(tid)
        except (LLMError, ValueError, TypeError, KeyError) as exc:
            result = FullUpdateResult(telegram_id=tid, error=str(exc))
            count = _increment_error(tid)
            logger.warning(
                "Unexpected error in full update for user %s: %s", tid, exc
            )
            if count >= 3:
                logger.error(
                    "3 consecutive update errors for user %s", tid
                )

        results.append(result)

    return results


async def update_single_user(telegram_id: int) -> FullUpdateResult:
    """Полное обновление памяти для одного пользователя (5 шагов).

    Не бросает исключений наружу (кроме непойманных).
    Ошибки записываются в result.error.
    Per-user lock предотвращает параллельные обновления.
    """
    lock = _get_update_lock(telegram_id)
    if lock.locked():
        logger.info("Update already running for %s, skipping", telegram_id)
        return FullUpdateResult(telegram_id=telegram_id)

    async with lock:
        return await _update_single_user_impl(telegram_id)


async def _update_single_user_impl(telegram_id: int) -> FullUpdateResult:
    """Реализация полного обновления (вызывается под мьютексом)."""
    result = FullUpdateResult(telegram_id=telegram_id)
    profile_updated = False
    procedural_updated = False
    pending_facts: list[dict] | None = None

    # --- Шаг 1: Загрузить сообщения ---
    user = await database.get_user(telegram_id)
    if user is None:
        result.error = f"User {telegram_id} not found"
        return result

    last_update = user.get("last_full_update_at")
    messages = await database.get_messages_since(
        telegram_id, since_dt=last_update or "2020-01-01"
    )

    if not messages:
        # Нет новых сообщений — ничего делать не нужно
        await database.update_user(
            telegram_id, needs_full_update=0, last_full_update_at=_now()
        )
        return result  # early exit, no error

    # Минимальный порог: не обновлять если < 3 user-сообщений
    user_messages = [m for m in messages if m.get("role") == "user"]
    if len(user_messages) < 3:
        logger.info(
            "Only %d user messages for %s, skipping update (min 3)",
            len(user_messages), telegram_id,
        )
        return result  # НЕ сбрасываем needs_full_update — ждём больше сообщений

    # --- Шаг 2: Создать конспект эпизода (с защитой от дубликатов) ---
    ep = None
    try:
        # Проверяем дубликат: есть ли недавний эпизод?
        headers = await database.get_episode_headers(telegram_id)
        existing_episode = None
        if headers:
            last_header = headers[0]  # самый свежий (ORDER BY created_at DESC)
            since_dt = last_update or "2020-01-01"
            if last_header.get("created_at") and last_header["created_at"] >= since_dt:
                existing_episode = last_header

        if existing_episode is None:
            ep = await episode_manager.create_episode(telegram_id, messages)
        else:
            # Используем существующий — загружаем полные данные
            episodes_full = await database.get_episodes_by_ids(
                [existing_episode["id"]]
            )
            if episodes_full:
                ep_dict = episodes_full[0]
                ep = type("EpisodeLike", (), {
                    "id": ep_dict["id"],
                    "summary": ep_dict.get("summary", ""),
                    "techniques_worked": ep_dict.get("techniques_worked_json", []),
                    "techniques_failed": ep_dict.get("techniques_failed_json", []),
                })()
            else:
                ep = await episode_manager.create_episode(telegram_id, messages)

        result.episode_id = getattr(ep, "id", None)

    except LLMError as exc:
        result.error = str(exc)
        return result  # без эпизода дальше не идём

    # --- Шаг 2b: Обновить running summary ---
    try:
        old_summary = await database.get_running_summary(telegram_id)
        new_summary = await _update_running_summary(old_summary, messages)
        await database.save_running_summary(telegram_id, new_summary)
    except (LLMError, ValueError, TypeError) as exc:
        logger.warning(
            "Running summary update failed for %s: %s", telegram_id, exc
        )

    # --- Шаг 3: Обновить профиль ---
    try:
        current_profile = await profile_manager.get_profile(telegram_id)
        if current_profile is None:
            current_profile = await profile_manager.create_empty_profile(telegram_id)
        pending_facts = await database.get_pending_facts(telegram_id)

        # Форматируем сообщения для промпта (последние 20)
        formatted = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages[-20:]
        )

        ep_summary = getattr(ep, "summary", "") if ep else ""

        prompt = PROFILE_UPDATE_PROMPT.format(
            current_profile=(
                current_profile.model_dump_json() if current_profile else "{}"
            ),
            new_messages=formatted,
            episode_summary=ep_summary,
            pending_facts=_format_facts(pending_facts),
        )

        raw = await call_gpt(
            messages=[{"role": "user", "content": prompt}],
            timeout=15,
            response_format={"type": "json_object"},
        )
        logger.info(
            "GPT profile response for %s: %s", telegram_id, raw[:500]
        )
        diff = json.loads(raw)

        if diff.get("set_fields") or diff.get("add_to_lists"):
            profile_diff = ProfileDiff(
                set_fields=diff.get("set_fields", {}),
                add_to_lists=diff.get("add_to_lists", {}),
                remove_fields=diff.get("remove_fields", []),
            )
            await profile_manager.update_profile(telegram_id, profile_diff)
            profile_updated = True

    except (LLMError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "Profile update failed for user %s: %s", telegram_id, exc
        )
        if not result.error:
            result.error = str(exc)
        # Продолжаем к шагу 4 — эпизод уже создан

    # --- Шаг 3b: Сжатие running summary (без GPT) ---
    try:
        current_summary = await database.get_running_summary(telegram_id)
        if current_summary and len(current_summary.split()) > 400:
            profile_data = current_profile.model_dump() if current_profile else {}
            filled = sum(
                1 for v in profile_data.values()
                if v and v != [] and v != {}
            )
            if filled >= 5 and profile_updated:
                words = current_summary.split()
                trimmed = " ".join(words[-200:])
                await database.save_running_summary(telegram_id, trimmed)
                logger.info(
                    "Running summary trimmed for %s (%d→200 words)",
                    telegram_id, len(words),
                )
    except Exception as exc:
        logger.warning(
            "Summary trim failed for %s: %s", telegram_id, exc
        )

    # --- Шаг 4: Обновить процедурную память ---
    try:
        techniques_worked = getattr(ep, "techniques_worked", []) or []
        techniques_failed = getattr(ep, "techniques_failed", []) or []

        if techniques_worked or techniques_failed:
            await procedural_memory.update_procedural(telegram_id, {
                "what_works": techniques_worked,
                "what_doesnt": techniques_failed,
            })
            procedural_updated = True

    except (ValueError, TypeError) as exc:
        logger.warning(
            "Procedural update failed for user %s: %s", telegram_id, exc
        )
        if not result.error:
            result.error = str(exc)

    # --- Шаг 5: Финализация ---
    pending_count = len(pending_facts) if pending_facts else 0

    try:
        await database.clear_pending_facts(telegram_id)
        await database.update_user(
            telegram_id,
            needs_full_update=0,
            last_full_update_at=_now(),
        )
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Finalization failed for user %s: %s", telegram_id, exc
        )
        if not result.error:
            result.error = str(exc)

    # Заполняем результат
    result.profile_updated = profile_updated
    result.procedural_updated = procedural_updated
    result.pending_facts_processed = pending_count

    # TODO: шаг 14 — ask_feeling(telegram_id, episode_id)

    return result
