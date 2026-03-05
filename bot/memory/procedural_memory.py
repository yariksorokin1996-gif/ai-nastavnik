"""
Процедурная память: КАК работать с пользователем.

Хранит что работает, что не работает, стиль коммуникации.
MERGE-логика: списки расширяются (без дублей), dict обновляется.
"""

import logging
from typing import Optional

from pydantic import ValidationError

from bot.memory import database
from shared.models import ProceduralMemory

logger = logging.getLogger(__name__)

# Максимум токенов для текстового представления
_MAX_TOKENS = 300
# Коэффициент: ~3.3 токена на слово
_TOKENS_PER_WORD = 3.3

_RELEVANT_KEYS = frozenset({"what_works", "what_doesnt", "communication_style"})


def _estimate_tokens(text: str) -> int:
    """Оценка количества токенов: слова * 3.3."""
    if not text:
        return 0
    return int(len(text.split()) * _TOKENS_PER_WORD)


def _merge_list(current: list[str], new_items: list[str]) -> list[str]:
    """Extend списка без дубликатов, сохраняя порядок."""
    result = list(current)
    for item in new_items:
        if item not in result:
            result.append(item)
    return result


async def get_procedural(telegram_id: int) -> Optional[ProceduralMemory]:
    """
    Получить процедурную память пользователя.

    Контракт:
      Вход: telegram_id
      Выход: ProceduralMemory | None
      Ошибки: ValidationError при невалидном JSON -> логируем, return None.
              DB-ошибки НЕ глотаем (пусть всплывают).
    """
    row = await database.get_procedural(telegram_id)
    if row is None:
        return None

    memory_json = row.get("memory_json")
    if memory_json is None:
        return None

    try:
        return ProceduralMemory(**memory_json)
    except (TypeError, ValidationError) as exc:
        logger.error(
            "get_procedural: ошибка парсинга для user=%s: %s | data=%r",
            telegram_id,
            exc,
            memory_json,
        )
        return None


async def update_procedural(
    telegram_id: int,
    updates: dict,
) -> ProceduralMemory:
    """
    Обновить процедурную память (MERGE, не replace).

    Контракт:
      Вход: telegram_id, updates (what_works, what_doesnt, communication_style)
      Выход: ProceduralMemory (обновлённая)
      Ошибки: DB-ошибки НЕ глотаем.
    """
    # Фильтруем только релевантные ключи
    relevant = {k: v for k, v in updates.items() if k in _RELEVANT_KEYS}

    # Получаем текущее состояние
    current = await get_procedural(telegram_id)

    # Если нет обновлений — no-op
    if not relevant:
        return current if current is not None else ProceduralMemory()

    # Если текущего нет — создаём пустой
    if current is None:
        current = ProceduralMemory()

    # MERGE
    if "what_works" in relevant:
        current.what_works = _merge_list(
            current.what_works, relevant["what_works"]
        )

    if "what_doesnt" in relevant:
        current.what_doesnt = _merge_list(
            current.what_doesnt, relevant["what_doesnt"]
        )

    if "communication_style" in relevant:
        current.communication_style.update(relevant["communication_style"])

    # Оценка токенов
    text = await get_procedural_as_text(telegram_id, _memory=current)
    tokens_count = _estimate_tokens(text)

    # Сохраняем
    await database.upsert_procedural(
        telegram_id, current.model_dump(), tokens_count
    )

    return current


async def get_procedural_as_text(
    telegram_id: int,
    *,
    _memory: Optional[ProceduralMemory] = None,
) -> str:
    """
    Текстовое представление процедурной памяти для промта.

    Контракт:
      Вход: telegram_id
      Выход: str (может быть пустой)
      Ошибки: DB-ошибки НЕ глотаем.

    _memory — внутренний параметр, чтобы не делать лишний запрос к БД
    при вызове из update_procedural.
    """
    memory = _memory if _memory is not None else await get_procedural(telegram_id)
    if memory is None:
        return ""

    lines: list[str] = []
    lines.append("=== КАК С НЕЙ РАБОТАТЬ ===")

    if memory.what_works:
        lines.append(f"✅ Работает: {', '.join(memory.what_works)}")

    if memory.what_doesnt:
        lines.append(f"❌ Не работает: {', '.join(memory.what_doesnt)}")

    if memory.communication_style:
        style_parts = [
            f"{k}: {v}" for k, v in memory.communication_style.items()
        ]
        lines.append(f"💬 Стиль: {', '.join(style_parts)}")

    # Только заголовок — нет полезных данных
    if len(lines) <= 1:
        return ""

    text = "\n".join(lines)

    # Проверка лимита токенов, обрезка при необходимости
    tokens = _estimate_tokens(text)
    if tokens > _MAX_TOKENS:
        text = _truncate_to_budget(memory, _MAX_TOKENS)

    return text


def _truncate_to_budget(memory: ProceduralMemory, max_tokens: int) -> str:
    """Обрезает списки, пока текст не уложится в бюджет токенов."""
    # Начинаем с полных списков и уменьшаем по одному элементу
    works = list(memory.what_works)
    doesnt = list(memory.what_doesnt)
    style = dict(memory.communication_style)

    while True:
        lines = ["=== КАК С НЕЙ РАБОТАТЬ ==="]
        if works:
            lines.append(f"✅ Работает: {', '.join(works)}")
        if doesnt:
            lines.append(f"❌ Не работает: {', '.join(doesnt)}")
        if style:
            style_parts = [f"{k}: {v}" for k, v in style.items()]
            lines.append(f"💬 Стиль: {', '.join(style_parts)}")

        text = "\n".join(lines)
        if _estimate_tokens(text) <= max_tokens:
            return text

        # Обрезаем самый длинный список на 1 элемент
        longest = max(
            [("works", len(works)), ("doesnt", len(doesnt))],
            key=lambda x: x[1],
        )
        if longest[1] == 0:
            # Списки пустые, обрезать нечего — возвращаем как есть
            return text
        if longest[0] == "works":
            works.pop()
        else:
            doesnt.pop()
