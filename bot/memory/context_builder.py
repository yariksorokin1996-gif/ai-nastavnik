"""
Сборщик контекстного окна для Claude.

Контракт:
    Вход: telegram_id (int), current_message (str)
    Выход: (system_prompt: str, token_count: int, meta: ContextMeta)
    Ошибки: ValueError если пользователь не найден,
            DB-ошибки в get_user пробрасываются наверх.
            Ошибки зависимостей — _safe_call ловит, секция пропускается.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bot.memory import database
from bot.memory.episode_manager import find_relevant_episodes
from bot.memory.procedural_memory import get_procedural_as_text
from bot.memory.profile_manager import get_profile_as_text
from bot.prompts.system_prompt import build_system_prompt
from shared.config import TOKEN_BUDGET_SOFT
from shared.models import ContextMeta, Episode

logger = logging.getLogger(__name__)

_FALLBACK_PROFILE = "=== ПРОФИЛЬ ===\nНовый пользователь. Информации пока нет. Наблюдай."
_FALLBACK_PROCEDURAL = "=== КАК С НЕЙ РАБОТАТЬ ===\nСтиль не определён. Наблюдай и подстраивайся."


# ---------------------------------------------------------------------------
# Внутренние хелперы
# ---------------------------------------------------------------------------


async def _safe_call(fn, *args, **kwargs):
    """Обёртка: при ошибке возвращает None + logger.warning."""
    try:
        return await fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("build_context: %s failed: %s", getattr(fn, "__name__", str(fn)), exc)
        return None


def _estimate_tokens(text: str) -> int:
    """Грубая оценка токенов: ~3.3 на слово."""
    if not text:
        return 0
    return int(len(text.split()) * 3.3)


def _calc_pause(last_message_at: str | None) -> int | None:
    """Возвращает минуты паузы или None (если < 60 мин или невалидная дата)."""
    if not last_message_at:
        return None
    try:
        # SQLite datetime формат: "YYYY-MM-DD HH:MM:SS"
        dt = datetime.strptime(last_message_at, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc,
        )
    except (ValueError, TypeError):
        return None
    diff = datetime.now(timezone.utc) - dt
    minutes = int(diff.total_seconds() / 60)
    return minutes if minutes >= 60 else None


def _format_episodes(episodes: list[Episode], limit: int = 3) -> str:
    """Форматирует эпизоды: '=== КОНТЕКСТ ПРОШЛЫХ РАЗГОВОРОВ ==='."""
    if not episodes:
        return ""
    lines = ["=== КОНТЕКСТ ПРОШЛЫХ РАЗГОВОРОВ ==="]
    for ep in episodes[:limit]:
        header = f"- {ep.title}"
        if ep.emotional_tone:
            header += f" ({ep.emotional_tone})"
        lines.append(header)
        if ep.summary:
            lines.append(f"  {ep.summary}")
        if ep.key_insight:
            lines.append(f"  Инсайт: {ep.key_insight}")
    return "\n".join(lines)


def _format_patterns(patterns: list[dict], limit: int = 5) -> str:
    """Форматирует паттерны: '=== ПАТТЕРНЫ ==='."""
    if not patterns:
        return ""
    lines = ["=== ПАТТЕРНЫ ==="]
    for p in patterns[:limit]:
        count = p.get("count", 1)
        lines.append(f"- {p.get('pattern_text', '')} (x{count})")
    return "\n".join(lines)


def _format_commitments(
    goal: dict | None,
    steps: list[dict] | None,
    only_pending: bool = False,
) -> str:
    """Форматирует цель и шаги: '=== ТЕКУЩАЯ ЦЕЛЬ ==='."""
    if not goal:
        return ""
    lines = [f"=== ТЕКУЩАЯ ЦЕЛЬ ===\n{goal.get('title', '')}"]
    if steps:
        for s in steps:
            if only_pending and s.get("status") == "completed":
                continue
            mark = "☑" if s.get("status") == "completed" else "☐"
            line = f"{mark} {s.get('title', '')}"
            if s.get("deadline_at"):
                line += f" (до {s['deadline_at']})"
            lines.append(line)
    return "\n".join(lines)


def _format_pause(pause_minutes: int) -> str:
    """Форматирует паузу в человекочитаемый вид."""
    if pause_minutes < 60:
        return ""
    if pause_minutes < 1440:
        hours = pause_minutes // 60
        return f"Пауза {hours} ч."
    days = pause_minutes // 1440
    return f"Пауза {days} дн."


# ---------------------------------------------------------------------------
# Обрезка по приоритетам
# ---------------------------------------------------------------------------


def _truncate_context(
    sections: dict[str, str],
    raw_episodes: list[Episode] | None,
    raw_patterns: list[dict] | None,
    raw_goal: dict | None,
    raw_steps: list[dict] | None,
) -> list[str]:
    """Обрезает секции пока total <= TOKEN_BUDGET_SOFT. Возвращает имена обрезанных."""
    truncated: list[str] = []

    def _total() -> int:
        return sum(_estimate_tokens(v) for v in sections.values() if v)

    # Приоритет 1: pause_context — удалить
    if _total() > TOKEN_BUDGET_SOFT and sections.get("pause_context"):
        sections["pause_context"] = ""
        truncated.append("pause_context")

    # Приоритет 2: commitments — только pending шаги
    if _total() > TOKEN_BUDGET_SOFT and sections.get("commitments"):
        sections["commitments"] = _format_commitments(raw_goal, raw_steps, only_pending=True)
        truncated.append("commitments")

    # Приоритет 3: patterns — top 3
    if _total() > TOKEN_BUDGET_SOFT and sections.get("patterns") and raw_patterns:
        sections["patterns"] = _format_patterns(raw_patterns, limit=3)
        truncated.append("patterns")

    # Приоритет 4: episodes — 2 вместо 3
    if _total() > TOKEN_BUDGET_SOFT and sections.get("episodes") and raw_episodes:
        sections["episodes"] = _format_episodes(raw_episodes, limit=2)
        truncated.append("episodes")

    # Приоритет 4.5: running_summary — обрезать до 150 слов
    if _total() > TOKEN_BUDGET_SOFT and sections.get("running_summary"):
        words = sections["running_summary"].split()
        if len(words) > 150:
            sections["running_summary"] = " ".join(words[:150]) + "..."
            truncated.append("running_summary")

    # Приоритет 5: profile — структурная обрезка (сначала strengths/achievements, потом с конца)
    if _total() > TOKEN_BUDGET_SOFT and sections.get("profile"):
        lines = sections["profile"].split("\n")
        # Сначала убрать менее важные секции (сильные стороны, достижения)
        low_priority = ("сильные стороны", "достижения", "strengths", "achievements")
        lines = [
            ln for ln in lines
            if not any(kw in ln.lower() for kw in low_priority)
        ]
        # Если всё ещё большой — обрезать с конца, сохраняя заголовок + первые строки
        while _estimate_tokens("\n".join(lines)) > 700 and len(lines) > 3:
            lines.pop()
        sections["profile"] = "\n".join(lines)
        truncated.append("profile")

    # Приоритет 6: procedural — только "Работает", убрать "Не работает"
    if _total() > TOKEN_BUDGET_SOFT and sections.get("procedural"):
        proc_lines = sections["procedural"].split("\n")
        proc_lines = [ln for ln in proc_lines if "Не работает" not in ln]
        sections["procedural"] = "\n".join(proc_lines)
        truncated.append("procedural")

    return truncated


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


async def build_context(
    telegram_id: int,
    current_message: str,
) -> tuple[str, int, ContextMeta]:
    """Собирает контекстное окно для Claude.

    Возвращает (system_prompt, token_count, ContextMeta).
    """
    # Шаг 1: пользователь (DB-ошибки пробрасываются)
    user = await database.get_user(telegram_id)
    if not user:
        raise ValueError(f"User {telegram_id} not found")

    current_phase = user.get("current_phase", "ЗНАКОМСТВО")
    pause_minutes = _calc_pause(user.get("last_message_at"))

    # Шаг 2: параллельный сбор данных
    profile_text, procedural_text, episodes, patterns, goal, running_summary, pending_facts = (
        await asyncio.gather(
            _safe_call(get_profile_as_text, telegram_id),
            _safe_call(get_procedural_as_text, telegram_id),
            _safe_call(find_relevant_episodes, telegram_id, current_message, limit=3),
            _safe_call(database.get_patterns, telegram_id),
            _safe_call(database.get_active_goal, telegram_id),
            _safe_call(database.get_running_summary, telegram_id),
            _safe_call(database.get_pending_facts, telegram_id),
        )
    )

    # Шаги цели (если есть)
    steps: list[dict] | None = None
    if goal and goal.get("id"):
        steps = await _safe_call(database.get_goal_steps, goal["id"])

    # Шаг 3: base prompt (SYNC вызов)
    conversation_mode = user.get("conversation_mode")
    base_prompt = build_system_prompt(current_phase, conversation_mode=conversation_mode)

    # Шаг 4: форматирование секций
    sections: dict[str, str] = {}
    sections["base_prompt"] = base_prompt

    sections["profile"] = profile_text if profile_text else _FALLBACK_PROFILE
    sections["procedural"] = procedural_text if procedural_text else _FALLBACK_PROCEDURAL

    if running_summary:
        sections["running_summary"] = f"=== СОДЕРЖАНИЕ РАЗГОВОРА ===\n{running_summary}"
    else:
        sections["running_summary"] = ""

    # Pending facts (из мини-обновлений regex) — имена, возраст, эмоции
    if pending_facts:
        facts_lines = []
        for f in pending_facts:
            ft = f.get("fact_type", "?")
            content = f.get("content", "?")
            facts_lines.append(f"- [{ft}] {content}")
        sections["pending_facts"] = (
            "=== СВЕЖИЕ ФАКТЫ (ещё не в профиле) ===\n" + "\n".join(facts_lines)
        )
    else:
        sections["pending_facts"] = ""

    sections["episodes"] = _format_episodes(episodes or [], limit=3)
    sections["patterns"] = _format_patterns(patterns or [], limit=5)
    sections["commitments"] = _format_commitments(goal, steps)

    if pause_minutes and pause_minutes >= 60:
        sections["pause_context"] = _format_pause(pause_minutes)
    else:
        sections["pause_context"] = ""

    # Шаг 5: обрезка если > TOKEN_BUDGET_SOFT
    truncated_vars = _truncate_context(
        sections, episodes, patterns, goal, steps,
    )

    # Шаг 6: проверка — если после всей обрезки всё ещё > 3800
    total = sum(_estimate_tokens(v) for v in sections.values() if v)
    if total > TOKEN_BUDGET_SOFT:
        logger.error(
            "build_context: total=%d > %d after full truncation, user=%s. "
            "Returning base_prompt only.",
            total, TOKEN_BUDGET_SOFT, telegram_id,
        )
        return (
            base_prompt,
            _estimate_tokens(base_prompt),
            ContextMeta(
                filled_vars=["base_prompt"],
                tokens_per_var={"base_prompt": _estimate_tokens(base_prompt)},
                was_truncated=True,
                truncated_vars=list(sections.keys()),
            ),
        )

    # Шаг 7: сборка (base_prompt ПЕРВЫМ для prompt caching)
    order = [
        "base_prompt", "profile", "pending_facts", "procedural",
        "running_summary", "episodes", "patterns", "commitments",
        "pause_context",
    ]
    parts = [sections[k] for k in order if sections.get(k)]
    final_prompt = "\n\n".join(parts)
    token_count = _estimate_tokens(final_prompt)

    meta = ContextMeta(
        filled_vars=[k for k in order if sections.get(k)],
        tokens_per_var={k: _estimate_tokens(sections[k]) for k in order if sections.get(k)},
        was_truncated=bool(truncated_vars),
        truncated_vars=truncated_vars,
    )

    return final_prompt, token_count, meta
