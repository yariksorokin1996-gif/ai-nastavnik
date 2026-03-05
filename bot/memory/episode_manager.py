"""Менеджер эпизодов: создание конспектов, поиск релевантных, список заголовков."""

import json
import logging
from datetime import datetime, timezone

from shared.llm_client import LLMError, call_gpt
from shared.models import Episode
from bot.memory import database
from bot.prompts.memory_prompts import EPISODE_SELECTION_PROMPT, EPISODE_SUMMARY_PROMPT

logger = logging.getLogger(__name__)


def _now() -> str:
    """UTC datetime строкой."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _format_messages(messages: list[dict]) -> str:
    """Форматирует список сообщений в текст 'role: content'."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_timestamps(messages: list[dict]) -> tuple[str, str]:
    """Извлекает session_start и session_end из timestamps сообщений.

    Если timestamps нет — возвращает текущее время для обоих.
    """
    now = _now()
    timestamps = [msg.get("created_at") for msg in messages if msg.get("created_at")]
    if not timestamps:
        return now, now
    return timestamps[0], timestamps[-1]


def _parse_episode_json(raw: str) -> Episode:
    """Парсит JSON-ответ LLM в Episode. При невалидном JSON — fallback."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("_parse_episode_json: невалидный JSON: %s", exc)
        return Episode(
            title="Разговор",
            summary="",
            emotional_tone="",
            key_insight=None,
            commitments=[],
            techniques_worked=[],
            techniques_failed=[],
        )

    return Episode(
        title=data.get("title", "Разговор"),
        summary=data.get("summary", ""),
        emotional_tone=data.get("emotional_tone", ""),
        key_insight=data.get("key_insight"),
        commitments=data.get("commitments", []),
        techniques_worked=data.get("techniques_worked", []),
        techniques_failed=data.get("techniques_failed", []),
    )


def _map_dict_to_episode(d: dict) -> Episode:
    """Маппинг словаря из БД в Episode."""
    return Episode(
        id=d["id"],
        title=d["title"],
        summary=d["summary"],
        emotional_tone=d.get("emotional_tone", ""),
        key_insight=d.get("key_insight"),
        commitments=d.get("commitments_json", []),
        techniques_worked=d.get("techniques_worked_json", []),
        techniques_failed=d.get("techniques_failed_json", []),
    )


def _keyword_fallback(
    current_message: str,
    headers: list[dict],
    limit: int,
) -> list[int]:
    """Keyword fallback: ищет совпадения слов из сообщения в заголовках эпизодов.

    Возвращает список id подходящих эпизодов (не больше limit).
    """
    words = [w.lower() for w in current_message.split() if len(w) > 3]
    matched_ids: list[int] = []
    seen: set[int] = set()
    for header in headers:
        title_lower = header["title"].lower()
        for word in words:
            if word in title_lower and header["id"] not in seen:
                matched_ids.append(header["id"])
                seen.add(header["id"])
                break
        if len(matched_ids) >= limit:
            break
    return matched_ids


# ---------------------------------------------------------------------------
# Публичные функции
# ---------------------------------------------------------------------------


async def create_episode(telegram_id: int, messages: list[dict]) -> Episode:
    """Создаёт конспект разговора из списка сообщений.

    При пустом messages — Episode с title='Пустой разговор'.
    При невалидном JSON от LLM — fallback Episode.
    При LLMError — пробрасывает наверх.
    """
    if not messages:
        return Episode(title="Пустой разговор", summary="", emotional_tone="")

    formatted = _format_messages(messages)
    session_start, session_end = _extract_timestamps(messages)

    # LLMError пробрасывается — вызывающий код решает
    response = await call_gpt(
        messages=[{"role": "user", "content": formatted}],
        system=EPISODE_SUMMARY_PROMPT,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    episode = _parse_episode_json(response)

    episode_id = await database.create_episode(
        telegram_id=telegram_id,
        title=episode.title,
        summary=episode.summary,
        emotional_tone=episode.emotional_tone,
        key_insight=episode.key_insight,
        commitments_json=episode.commitments,
        techniques_worked_json=episode.techniques_worked,
        techniques_failed_json=episode.techniques_failed,
        messages_count=len(messages),
        session_start=session_start,
        session_end=session_end,
    )

    episode.id = episode_id
    logger.info(
        "create_episode: user=%s episode_id=%d title=%r",
        telegram_id, episode_id, episode.title,
    )
    return episode


async def find_relevant_episodes(
    telegram_id: int,
    current_message: str,
    limit: int = 3,
) -> list[Episode]:
    """Находит релевантные эпизоды для текущего сообщения.

    Использует LLM для семантического подбора.
    При LLMError или невалидном JSON — keyword fallback.
    """
    headers = await database.get_episode_headers(telegram_id)
    if not headers:
        return []

    # Нумерованный список заголовков
    episode_list = "\n".join(
        f"{i + 1} \u2014 {h['title']}" for i, h in enumerate(headers)
    )

    prompt = EPISODE_SELECTION_PROMPT.format(
        current_message=current_message,
        episode_list=episode_list,
    )

    selected_ids: list[int] = []
    try:
        response = await call_gpt(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        data = json.loads(response)
        selected_numbers = data.get("selected", [])

        # Маппинг номеров (1-based) на реальные ID
        for num in selected_numbers:
            if isinstance(num, int) and 1 <= num <= len(headers):
                selected_ids.append(headers[num - 1]["id"])
        selected_ids = selected_ids[:limit]

    except LLMError:
        logger.warning(
            "find_relevant_episodes: LLMError, keyword fallback user=%s",
            telegram_id,
        )
        selected_ids = _keyword_fallback(current_message, headers, limit)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning(
            "find_relevant_episodes: невалидный JSON (%s), keyword fallback user=%s",
            exc, telegram_id,
        )
        selected_ids = _keyword_fallback(current_message, headers, limit)

    if not selected_ids:
        return []

    rows = await database.get_episodes_by_ids(selected_ids)
    return [_map_dict_to_episode(row) for row in rows]


async def get_episode_titles(telegram_id: int) -> list[str]:
    """Возвращает список заголовков всех эпизодов пользователя."""
    headers = await database.get_episode_headers(telegram_id)
    return [h["title"] for h in headers]
