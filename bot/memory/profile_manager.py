"""
Менеджер семантического профиля пользователя.

Контракт:
    Вход: telegram_id, SemanticProfile, ProfileDiff
    Выход: SemanticProfile | None | str
    Ошибки: ValueError (профиль/версия не найдены), aiosqlite.Error (пробрасываем)

5 функций: create_empty_profile, get_profile, update_profile,
           rollback_profile, get_profile_as_text.
"""

import logging
from typing import Optional

from pydantic import ValidationError

from bot.memory import database
from shared.models import PersonEntry, ProfileDiff, SemanticProfile

logger = logging.getLogger(__name__)

# Максимальный бюджет токенов для текстового представления профиля
_MAX_PROFILE_TOKENS = 1000

# Поля, которые обрезаются первыми при превышении бюджета (наименее важные)
_LOW_PRIORITY_FIELDS = ("achievements", "strengths")

# Порядок полей для текстового представления (label -> attr)
_PROFILE_TEXT_FIELDS = (
    ("Имя", "name"),
    ("Возраст", "age"),
    ("Город", "city"),
    ("Семья", "family"),
    ("Работа", "work"),
    ("Главная проблема", "main_problem"),
    ("Корневой паттерн", "root_pattern"),
    ("Текущая цель", "current_goal"),
    ("Стиль общения", "communication_style"),
    ("Триггеры", "triggers"),
    ("Сильные стороны", "strengths"),
    ("Достижения", "achievements"),
    ("Чувствительные темы", "sensitive_topics"),
)


def _estimate_tokens(text: str) -> int:
    """Грубая оценка количества токенов по числу слов."""
    return int(len(text.split()) * 3.3)


def _format_people(people: list[PersonEntry]) -> str:
    """Формат: 'Саша (муж), Настя (подруга)'."""
    parts = []
    for p in people:
        if p.relation:
            parts.append(f"{p.name} ({p.relation})")
        else:
            parts.append(p.name)
    return ", ".join(parts)


def _profile_to_text(
    profile: SemanticProfile,
    *,
    exclude_fields: tuple[str, ...] = (),
) -> str:
    """Преобразует профиль в текстовое представление, пропуская None-поля."""
    lines = ["=== ПРОФИЛЬ ==="]

    for label, attr in _PROFILE_TEXT_FIELDS:
        if attr in exclude_fields:
            continue
        value = getattr(profile, attr, None)
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{label}: {', '.join(str(v) for v in value)}")
        else:
            lines.append(f"{label}: {value}")

    # Люди — отдельно
    if profile.people and "people" not in exclude_fields:
        lines.append(f"Люди: {_format_people(profile.people)}")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# 1. create_empty_profile
# -------------------------------------------------------------------------


async def create_empty_profile(telegram_id: int) -> SemanticProfile:
    """Создаёт пустой профиль и сохраняет в БД."""
    profile = SemanticProfile()
    await database.upsert_profile(telegram_id, profile.model_dump(), tokens_count=0)
    logger.info("create_empty_profile: user=%s", telegram_id)
    return profile


# -------------------------------------------------------------------------
# 2. get_profile
# -------------------------------------------------------------------------


async def get_profile(telegram_id: int) -> Optional[SemanticProfile]:
    """Загружает профиль из БД. None если не найден или ошибка парсинга."""
    row = await database.get_profile(telegram_id)
    if row is None:
        return None
    try:
        return SemanticProfile(**row["profile_json"])
    except (TypeError, ValidationError):
        logger.error(
            "get_profile: ошибка парсинга profile_json для user=%s",
            telegram_id,
            exc_info=True,
        )
        return None


# -------------------------------------------------------------------------
# 3. update_profile
# -------------------------------------------------------------------------


async def update_profile(
    telegram_id: int,
    diff: ProfileDiff,
) -> SemanticProfile:
    """Применяет diff к текущему профилю и сохраняет."""
    profile = await get_profile(telegram_id)
    if profile is None:
        profile = await create_empty_profile(telegram_id)

    # No-op: пустой diff
    if not diff.set_fields and not diff.add_to_lists and not diff.remove_fields:
        return profile

    # set_fields (фильтруем поля вне схемы SemanticProfile)
    valid_fields = set(SemanticProfile.model_fields.keys())
    for key, value in diff.set_fields.items():
        if key not in valid_fields:
            logger.warning("update_profile: unknown field %r ignored", key)
            continue
        setattr(profile, key, value)

    # add_to_lists (extend без дублей)
    for key, items in diff.add_to_lists.items():
        if key == "people":
            _merge_people(profile, items)
        else:
            current = getattr(profile, key, None)
            if current is None:
                setattr(profile, key, list(items))
            else:
                for item in items:
                    if item not in current:
                        current.append(item)

    # remove_fields
    for key in diff.remove_fields:
        if hasattr(profile, key):
            # Сбрасываем в значение по умолчанию для поля
            field_info = SemanticProfile.model_fields.get(key)
            if field_info is not None:
                default = field_info.default
                if default is not None:
                    setattr(profile, key, default)
                else:
                    setattr(profile, key, None)

    # Оценка токенов
    text = _profile_to_text(profile)
    tokens_count = _estimate_tokens(text)

    await database.upsert_profile(telegram_id, profile.model_dump(), tokens_count)
    logger.info("update_profile: user=%s tokens=%d", telegram_id, tokens_count)
    return profile


def _merge_people(profile: SemanticProfile, new_people: list) -> None:
    """Дедупликация людей по name: обновить существующего если name совпадает."""
    existing_by_name: dict[str, int] = {
        p.name: idx for idx, p in enumerate(profile.people)
    }
    for item in new_people:
        person = PersonEntry(**item) if isinstance(item, dict) else item
        if person.name in existing_by_name:
            # Обновляем существующего
            profile.people[existing_by_name[person.name]] = person
        else:
            profile.people.append(person)
            existing_by_name[person.name] = len(profile.people) - 1


# -------------------------------------------------------------------------
# 4. rollback_profile
# -------------------------------------------------------------------------


async def rollback_profile(
    telegram_id: int,
    version: int,
) -> SemanticProfile:
    """Откатывает профиль к указанной версии."""
    profile_json = await database.get_profile_version(telegram_id, version)
    if profile_json is None:
        raise ValueError(f"Version {version} not found")

    profile = SemanticProfile(**profile_json)

    text = _profile_to_text(profile)
    tokens_count = _estimate_tokens(text)

    await database.upsert_profile(telegram_id, profile_json, tokens_count)
    logger.info(
        "rollback_profile: user=%s to version=%d",
        telegram_id,
        version,
    )
    return profile


# -------------------------------------------------------------------------
# 5. get_profile_as_text
# -------------------------------------------------------------------------


async def get_profile_as_text(telegram_id: int) -> str:
    """Текстовое представление профиля для промпта. Обрезает при > 1000 токенов."""
    profile = await get_profile(telegram_id)
    if profile is None:
        return ""

    text = _profile_to_text(profile)
    tokens = _estimate_tokens(text)

    if tokens > _MAX_PROFILE_TOKENS:
        # Убираем наименее важные поля
        text = _profile_to_text(profile, exclude_fields=_LOW_PRIORITY_FIELDS)
        logger.info(
            "get_profile_as_text: user=%s обрезан с %d до ~%d токенов",
            telegram_id,
            tokens,
            _estimate_tokens(text),
        )

    return text
