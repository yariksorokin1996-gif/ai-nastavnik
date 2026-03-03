# Спецификация: full_memory_update (APScheduler job)

## Назначение

Фоновая задача, запускаемая APScheduler каждые 5 минут. Находит пользователей с паузой >= 30 минут и выполняет полное обновление памяти: создаёт конспект эпизода, обновляет семантический профиль, обновляет процедурную память, запускает сбор обратной связи.

**Текущее состояние:** файл не существует, создаётся с нуля.

**Расположение:** `bot/memory/full_memory_update.py`

## Зависимости (6)

```python
from shared.llm_client import call_gpt, LLMError                  # GPT-4o-mini для анализа
from bot.memory.database import (
    get_users_needing_update,     # -> list[int]
    get_messages_since,           # -> list[dict]
    get_pending_facts,            # -> list[dict]
    clear_pending_facts,          # -> None
    update_user,                  # -> None
    get_user,                     # -> dict
)
from bot.memory.profile_manager import get_profile, update_profile  # семантический профиль
from bot.memory.episode_manager import create_episode               # создание конспекта
from bot.memory.procedural_memory import get_procedural, update_procedural
from bot.analytics.feedback_collector import ask_feeling            # сбор обратной связи
```

## Публичный API

### `async def run_full_memory_update() -> None`

APScheduler job. Вызывается каждые 5 минут. Не принимает аргументов, не возвращает значений.

**Пример регистрации:**

```python
# В bot/main.py или scheduler.py:
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(
    run_full_memory_update,
    trigger="interval",
    minutes=5,
    id="full_memory_update",
    replace_existing=True,
)
```

### `async def update_single_user(telegram_id: int) -> FullUpdateResult`

Обновление одного пользователя. Вызывается из `run_full_memory_update` для каждого пользователя.

**Вход:** telegram_id

**Выход:**
```python
class FullUpdateResult(BaseModel):
    telegram_id: int
    episode_id: int | None           # ID созданного эпизода
    profile_updated: bool            # был ли обновлён профиль
    procedural_updated: bool         # была ли обновлена процедурная
    pending_facts_processed: int     # сколько pending_facts обработано
    error: str | None                # ошибка (если была)
```

**Ошибки:**
- Не бросает исключений наружу. Ошибки ловятся внутри, записываются в `result.error`.
- 3 ошибки подряд для одного пользователя → `logger.error` + alert.
- `needs_full_update` остаётся `1` при ошибке (повторная попытка через 5 мин).

**Пример вызова:**

```python
result = await update_single_user(telegram_id=123456)

# Успех:
# result.episode_id → 42
# result.profile_updated → True
# result.procedural_updated → True
# result.pending_facts_processed → 5
# result.error → None

# Ошибка LLM:
# result.episode_id → None
# result.error → "LLMError: GPT-4o-mini timeout after 15s"
```

## Алгоритм run_full_memory_update

### Шаг 0: Найти пользователей для обновления

```python
async def run_full_memory_update():
    user_ids = await get_users_needing_update()
    # SQL: WHERE last_message_at < datetime('now', '-30 minutes')
    #        AND needs_full_update = 1

    if not user_ids:
        return

    for telegram_id in user_ids:
        try:
            result = await update_single_user(telegram_id)
            if result.error:
                logger.warning(f"Update failed for {telegram_id}: {result.error}")
                _increment_error_count(telegram_id)
                if _get_error_count(telegram_id) >= 3:
                    logger.error(f"3 consecutive errors for {telegram_id}, alerting owner")
                    await _alert_owner(telegram_id)
            else:
                _reset_error_count(telegram_id)
        except Exception as e:
            logger.error(f"Unexpected error for {telegram_id}: {e}")
```

## Алгоритм update_single_user (5 шагов)

### Шаг 1: Загрузить сессию сообщений

```python
user = await get_user(telegram_id)
last_update = user.get("last_full_update_at")  # ISO timestamp или None

messages = await get_messages_since(telegram_id, since_dt=last_update or "2020-01-01")

if not messages:
    # Нет новых сообщений → ничего делать не нужно
    await update_user(telegram_id, needs_full_update=0, last_full_update_at=_now())
    return FullUpdateResult(telegram_id=telegram_id, ...)
```

### Шаг 2: Создать конспект эпизода (GPT-4o-mini)

```python
episode = await create_episode(telegram_id, messages)
# Внутри create_episode:
#   prompt = EPISODE_SUMMARY_PROMPT.format(messages=formatted_messages)
#   response = await call_gpt(messages=[...], system=prompt, response_format={"type": "json_object"})
#   Парсит JSON: title, summary, emotional_tone, key_insight, commitments, techniques_worked/failed
#   Сохраняет в БД: episodes таблица
#   Возвращает: Episode(id, title, summary, ...)
```

**Промпт для конспекта:**
```
Проанализируй разговор и создай конспект. Ответь JSON:
{
  "title": "Краткое описание (≤20 слов)",
  "summary": "Конспект разговора (50-100 слов)",
  "emotional_tone": "тревога → облегчение",
  "key_insight": "Ключевой инсайт (1 предложение)",
  "commitments": ["обязательства из разговора"],
  "techniques_worked": ["что сработало в общении"],
  "techniques_failed": ["что не сработало"]
}
```

### Шаг 3: Обновить профиль (GPT-4o-mini)

```python
current_profile = await get_profile(telegram_id)
pending_facts = await get_pending_facts(telegram_id)

# Формируем запрос к GPT-4o-mini:
prompt = PROFILE_UPDATE_PROMPT.format(
    current_profile=current_profile.model_dump_json() if current_profile else "{}",
    new_messages=_format_messages(messages),
    pending_facts=_format_facts(pending_facts),
    episode_summary=episode.summary,
)

response = await call_gpt(
    messages=[{"role": "user", "content": prompt}],
    system="Обнови профиль пользователя. Ответь JSON.",
    response_format={"type": "json_object"},
)

# Парсим diff:
diff = json.loads(response)
# diff = {"set_fields": {"age": 32}, "add_to_lists": {"people": [...]}, "remove_fields": []}

if diff.get("set_fields") or diff.get("add_to_lists"):
    await update_profile(telegram_id, ProfileDiff(**diff))
    profile_updated = True
```

**Правила обновления профиля:**
- **MERGE, не перезапись.** Новые факты добавляются к существующим.
- **Уровни уверенности:** прямое высказывание → "high", из контекста → "medium", двусмысленно → skip.
- **Карта людей:** обновляется инкрементально. Человек добавляется/обновляется, но не удаляется.
- **Эмоции ≠ факты:** «мне грустно» → emotion_log, НЕ в профиль. «Мне 32 года» → профиль.

### Шаг 4: Обновить процедурную память

```python
# На основе techniques_worked/failed из эпизода:
if episode.techniques_worked or episode.techniques_failed:
    current_procedural = await get_procedural(telegram_id)
    updates = {
        "what_works": episode.techniques_worked or [],
        "what_doesnt": episode.techniques_failed or [],
    }
    await update_procedural(telegram_id, updates)
    procedural_updated = True
```

### Шаг 5: Финализация

```python
# Очистить pending_facts (уже обработаны в шаге 3):
await clear_pending_facts(telegram_id)

# Обновить статус пользователя:
await update_user(
    telegram_id,
    needs_full_update=0,
    last_full_update_at=_now(),
)

# Запросить обратную связь (если условия выполнены):
await _try_ask_feeling(telegram_id, episode.id)
```

### Сбор обратной связи (после финализации)

```python
async def _try_ask_feeling(telegram_id: int, episode_id: int):
    """Условия для запроса feeling_after:
    - Эпизод создан 2+ часов назад (т.к. мы только что создали — будет вызвано
      при СЛЕДУЮЩЕМ run_full_memory_update через 5+ мин, но на практике
      ask_feeling сама проверяет условия)
    - Нет session_feedback для этого episode_id
    - Пользователь не писал после session_end
    - >= 3 сообщений в сессии
    - Cooldown: max 1 раз в 8 часов
    """
    try:
        await ask_feeling(telegram_id, episode_id)
    except Exception as e:
        logger.warning(f"ask_feeling failed for {telegram_id}: {e}")
        # Не критично — пропускаем
```

## Счётчик ошибок

```python
# In-memory, сбрасывается при перезапуске (что безопасно):
_error_counts: dict[int, int] = {}

def _increment_error_count(telegram_id: int):
    _error_counts[telegram_id] = _error_counts.get(telegram_id, 0) + 1

def _get_error_count(telegram_id: int) -> int:
    return _error_counts.get(telegram_id, 0)

def _reset_error_count(telegram_id: int):
    _error_counts.pop(telegram_id, None)

async def _alert_owner(telegram_id: int):
    """Отправить alert владельцу через Telegram."""
    from bot.analytics.alerter import alerter
    await alerter.check(telegram_id, "consecutive_update_errors", _get_error_count(telegram_id))
```

## CRUD из database.py, которые используются

| Функция | Для чего |
|---------|---------|
| `get_users_needing_update()` | Шаг 0: найти юзеров с needs_full_update=1 и паузой >= 30 мин |
| `get_user(telegram_id)` | Шаг 1: last_full_update_at |
| `get_messages_since(telegram_id, since_dt)` | Шаг 1: все сообщения с последнего обновления |
| `get_profile(telegram_id)` | Шаг 3: текущий профиль для diff |
| `get_pending_facts(telegram_id)` | Шаг 3: буфер мини-обновлений |
| `clear_pending_facts(telegram_id)` | Шаг 5: очистить обработанные факты |
| `update_user(telegram_id, ...)` | Шаг 5: needs_full_update=0, last_full_update_at |

## Edge cases

1. **Нет сообщений в диапазоне:** needs_full_update=0, last_full_update_at обновляется. Нет ошибки.

2. **LLM timeout на шаге 2 (конспект):** retry 2 раза (встроен в call_gpt). Если всё равно ошибка → result.error, needs_full_update остаётся 1. Следующая попытка через 5 мин.

3. **LLM timeout на шаге 3 (профиль):** эпизод уже создан (шаг 2 прошёл). Профиль не обновляется. needs_full_update остаётся 1. При следующей попытке: шаг 1 загрузит те же сообщения, шаг 2 создаст дубль эпизода? → **НЕТ:** `last_full_update_at` обновляется только в шаге 5. Значит messages_since загрузит те же сообщения. Дубль эпизода возможен. → **Защита:** перед шагом 2 проверить: есть ли эпизод с session_end = last_message_at? Если да → пропустить шаг 2.

4. **pending_facts пустые:** шаг 3 всё равно выполняется (messages достаточно для обновления профиля).

5. **Пользователь пишет во время обновления:** WAL mode позволяет параллельную запись. Мьютекс session_manager не блокирует full_memory_update (они работают независимо). Новые сообщения попадут в следующее обновление.

6. **Несколько пользователей:** обрабатываются последовательно (не параллельно), чтобы не перегружать GPT-4o-mini.

## Что НЕ делать

- **НЕ использовать мьютекс session_manager.** full_memory_update работает без user lock. WAL mode SQLite обеспечивает консистентность.
- **НЕ удалять** данные из профиля. Только добавлять/обновлять (merge).
- **НЕ вызывать Claude** (Sonnet). Только GPT-4o-mini для фоновых задач.
- **НЕ блокировать** обработку сообщений. Это фоновая задача.
- **НЕ обрабатывать** пользователей параллельно (gather). Последовательно, один за другим.
- **НЕ сбрасывать** needs_full_update при ошибке. Оставить 1 для повторной попытки.

## Промпты (используются 2 промпта GPT-4o-mini)

1. **EPISODE_SUMMARY_PROMPT** — определён в `bot/prompts/memory_prompts.py`
2. **PROFILE_UPDATE_PROMPT** — определён в `bot/prompts/memory_prompts.py`

Оба промпта требуют response_format={"type": "json_object"}.
