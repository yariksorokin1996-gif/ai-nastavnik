# Спецификация: bot/session_manager.py

## Назначение

Главный модуль обработки входящих сообщений. Реализует 14-шаговый алгоритм: от получения сообщения до ответа + фоновое мини-обновление памяти. Управляет мьютексом, idempotency, rate limiting, кризисной маршрутизацией.

**Текущее состояние:** файл существует (198 строк), старая архитектура (5 фаз, «Алекс»). Полная переписка.

## Зависимости (10)

```python
from shared.llm_client import call_claude, LLMError             # Claude Sonnet для диалога
from bot.memory.context_builder import build_context             # сборка контекста (≤3800 tok)
from bot.memory.database import (
    is_message_processed,        # idempotency check
    mark_message_processed,      # пометить обработанным
    add_message,                 # сохранить сообщение
    get_recent_messages,         # последние 20 сообщений
    get_user,                    # данные пользователя
    update_user,                 # обновить счётчики
    add_pending_fact,            # мини-обновление (pending_facts)
    add_emotion,                 # эмоции (emotion_log)
)
from shared.safety import detect_crisis, CRISIS_RESPONSE_LEVEL3, CRISIS_INSTRUCTION_LEVEL2
from bot.transcriber import transcribe_voice                      # Whisper API
from bot.analytics.alerter import alerter                         # алерты при аномалиях
from shared.config import (
    RATE_LIMIT_PER_MINUTE,       # = 60
    CLAUDE_TIMEOUT,              # = 30
    TOKEN_BUDGET_SOFT,           # = 3800
    FALLBACK_RESPONSE,           # = "Мм, мне нужно немного подумать..."
)
from bot.prompts.phase_evaluator import evaluate_phase           # проверка фазы (каждые 10 msg)
from bot.memory.episode_manager import find_relevant_episodes    # (используется через context_builder)
```

## Публичный API

### `async def process_message(telegram_id: int, message_id: int, text: str | None, voice_file_id: str | None, user_name: str | None) -> str`

**Вход:**
- `telegram_id` — ID пользователя
- `message_id` — уникальный ID сообщения Telegram (для idempotency)
- `text` — текст сообщения (None если голосовое)
- `voice_file_id` — ID голосового файла (None если текстовое)
- `user_name` — имя пользователя (для первого создания)

**Выход:** `str` — ответ Евы для отправки пользователю.

**Ошибки:**
- Не бросает исключений наружу. При любой ошибке → возвращает FALLBACK_RESPONSE.
- Логирует все ошибки.

**Пример вызова (из handlers.py):**

```python
# Текстовое сообщение:
response = await process_message(
    telegram_id=123456,
    message_id=98765,
    text="Сегодня опять поругалась с мамой",
    voice_file_id=None,
    user_name="Маша",
)
# response → "Звучит, как будто это было непросто. Расскажи, что произошло?"

# Голосовое сообщение:
response = await process_message(
    telegram_id=123456,
    message_id=98766,
    text=None,
    voice_file_id="AwACAgIAAxkBAAI...",
    user_name="Маша",
)

# Дубль (idempotency):
response = await process_message(
    telegram_id=123456,
    message_id=98765,  # уже обработанный
    text="Сегодня опять поругалась с мамой",
    voice_file_id=None,
    user_name="Маша",
)
# response → None (пропуск, уже обработано)
```

## Внутреннее состояние (module-level)

```python
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

# Мьютекс: один Lock на пользователя (ленивое создание)
_user_locks: dict[int, asyncio.Lock] = {}

def _get_user_lock(telegram_id: int) -> asyncio.Lock:
    if telegram_id not in _user_locks:
        _user_locks[telegram_id] = asyncio.Lock()
    return _user_locks[telegram_id]

# Rate limiting: in-memory счётчик
_rate_counters: dict[int, list[float]] = {}  # telegram_id → [timestamps]

def _check_rate_limit(telegram_id: int) -> bool:
    """Возвращает True если лимит НЕ превышен."""
    now = time.time()
    timestamps = _rate_counters.get(telegram_id, [])
    # Убрать записи старше 60 секунд:
    timestamps = [t for t in timestamps if now - t < 60]
    _rate_counters[telegram_id] = timestamps
    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        return False
    timestamps.append(now)
    return True

# Счётчик последовательных ошибок (для alerter):
_consecutive_errors: dict[int, int] = {}
```

## Алгоритм: 14 шагов

### Шаг 1: Получить сообщение

```python
async def process_message(telegram_id, message_id, text, voice_file_id, user_name) -> str | None:
    start_time = time.monotonic()
```

### Шаг 2: Проверка idempotency

```python
    if await is_message_processed(message_id):
        logger.debug(f"Message {message_id} already processed, skipping")
        return None
```

### Шаг 3: Захватить мьютекс пользователя

```python
    lock = _get_user_lock(telegram_id)
    async with lock:
        return await _process_under_lock(
            telegram_id, message_id, text, voice_file_id, user_name, start_time
        )
```

### Шаг 4: Определить длину паузы

```python
async def _process_under_lock(telegram_id, message_id, text, voice_file_id, user_name, start_time):
    user = await get_user(telegram_id)
    if not user:
        user = await create_user(telegram_id, name=user_name)

    last_msg_at = user.get("last_message_at")
    pause_minutes = _calc_pause_minutes(last_msg_at) if last_msg_at else None
```

### Шаг 5: Конвертировать голосовое → текст

```python
    is_voice = False
    if voice_file_id and not text:
        is_voice = True
        try:
            text = await transcribe_voice(voice_file_id)
            # transcribe_voice: Whisper API, лимит 3 мин, timeout 30 сек
        except Exception as e:
            logger.warning(f"Voice transcription failed: {e}")
            text = None

    if not text:
        return "Прости, не расслышала. Напиши текстом?"
```

### Шаг 6: Проверить кризис

```python
    crisis = detect_crisis(text)
    # crisis = {"level": 0|1|2|3, "trigger": str|None, "is_verified": bool}

    if crisis["level"] == 3:
        # Суицид → шаблонный ответ, Claude НЕ вызывается
        await add_message(telegram_id, role="user", content=text, source="user",
                          is_voice=int(is_voice))
        await add_message(telegram_id, role="assistant", content=CRISIS_RESPONSE_LEVEL3,
                          source="crisis")
        await mark_message_processed(message_id, telegram_id)
        await alerter.check(telegram_id, "crisis_level_3")
        return CRISIS_RESPONSE_LEVEL3
```

### Шаг 7: Проверить rate limit

```python
    if not _check_rate_limit(telegram_id):
        logger.warning(f"Rate limit exceeded for {telegram_id}")
        return "Подожди немного, я не успеваю. Напиши через минутку."
```

### Шаг 8: Сохранить входящее сообщение

```python
    await add_message(
        telegram_id, role="user", content=text, source="user",
        is_voice=int(is_voice), char_length=len(text),
    )
    await mark_message_processed(message_id, telegram_id)
```

### Шаг 9: Собрать контекст

```python
    try:
        system_prompt, token_count, meta = await build_context(telegram_id, text)
    except Exception as e:
        logger.error(f"build_context failed: {e}")
        await alerter.check(telegram_id, "consecutive_empty_context")
        system_prompt = None

    if not system_prompt:
        # Fallback: минимальный контекст
        return FALLBACK_RESPONSE
```

### Шаг 10: Отправить запрос Claude Sonnet

```python
    # Подготовить историю сообщений (последние 20):
    recent_messages = await get_recent_messages(telegram_id, limit=20)
    messages_for_claude = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in recent_messages
    ]

    # Добавить кризисную инструкцию уровня 2 если нужно:
    if crisis["level"] == 2:
        system_prompt += f"\n\n{CRISIS_INSTRUCTION_LEVEL2}"

    try:
        response = await call_claude(
            messages=messages_for_claude,
            system=system_prompt,
            max_tokens=500,
            timeout=CLAUDE_TIMEOUT,  # 30 сек
        )
    except LLMError as e:
        logger.error(f"Claude call failed: {e}")
        _consecutive_errors[telegram_id] = _consecutive_errors.get(telegram_id, 0) + 1
        if _consecutive_errors.get(telegram_id, 0) >= 3:
            await alerter.check(telegram_id, "consecutive_errors", 3)
        return FALLBACK_RESPONSE

    # Сбросить счётчик ошибок при успехе:
    _consecutive_errors.pop(telegram_id, None)
```

### Шаг 11: Сохранить ответ

```python
    # Замерить latency:
    latency_ms = int((time.monotonic() - start_time) * 1000)

    await add_message(
        telegram_id, role="assistant", content=response, source="user",
        response_latency_ms=latency_ms, char_length=len(response),
    )

    # Проверить latency для alerter:
    if latency_ms > 25000:
        await alerter.check(telegram_id, "latency_critical_ms", latency_ms)
```

### Шаг 12: Мини-обновление памяти (ASYNC, не блокирует)

```python
    # Запускаем в фоне — НЕ ждём результата:
    asyncio.create_task(_mini_memory_update(telegram_id, text, response))
```

### Шаг 13: Проверка фазы (ASYNC, каждые 10 сообщений)

```python
    messages_total = user.get("messages_total", 0) + 1
    if messages_total % 10 == 0:
        asyncio.create_task(_check_phase_transition(telegram_id))
```

### Шаг 14: Обновить счётчики

```python
    await update_user(
        telegram_id,
        last_message_at=_now(),
        messages_total=messages_total,
        needs_full_update=1,
    )

    return response
```

## Внутренние функции

### `_mini_memory_update(telegram_id: int, user_text: str, bot_response: str)`

Мини-обновление памяти через regex (без LLM). Не блокирует ответ.

```python
async def _mini_memory_update(telegram_id: int, user_text: str, bot_response: str):
    """Извлечение фактов из сообщения (regex, без LLM)."""
    try:
        # 1. Имена людей:
        #    Regex: мо[йяиюей]\s+([А-ЯЁ][а-яё]{2,})
        #    Стоп-лист: Бог, Господь, Инстаграм, Телеграм, Россия, Москва...
        names = _extract_names(user_text)
        for name in names:
            await add_pending_fact(telegram_id, "person", name, confidence="medium")

        # 2. Обязательства:
        #    Regex: (завтра|на этой неделе|обещаю|попробую|планирую)\s+(.+)
        commitments = _extract_commitments(user_text)
        for c in commitments:
            await add_pending_fact(telegram_id, "commitment", c, confidence="medium")

        # 3. Возраст:
        #    Regex: мне\s+(\d{2})\s+(год|лет|года)
        age = _extract_age(user_text)
        if age:
            await add_pending_fact(telegram_id, "age", str(age), confidence="high")

        # 4. Эмоции:
        #    Словарь: злость, грусть, радость, тревога, усталость
        emotions = _extract_emotions(user_text)
        for emotion in emotions:
            await add_emotion(telegram_id, emotion)

    except Exception as e:
        logger.warning(f"Mini memory update failed: {e}")
        # Не критично — продолжаем
```

### `_check_phase_transition(telegram_id: int)`

Проверка готовности к переходу на следующую фазу.

```python
async def _check_phase_transition(telegram_id: int):
    """Вызывается каждые 10 сообщений. Использует GPT-4o-mini."""
    try:
        user = await get_user(telegram_id)
        current_phase = user.get("current_phase", "ЗНАКОМСТВО")
        messages_total = user.get("messages_total", 0)

        # Минимальные пороги (не проверяем раньше):
        PHASE_THRESHOLDS = {
            "ЗНАКОМСТВО": 6,
            "ЗЕРКАЛО": 15,
            "НАСТРОЙКА": 25,
            "ПОРТРЕТ": 40,
            "ЦЕЛЬ": 50,
            "РИТМ": None,  # финальная фаза
        }

        min_messages = PHASE_THRESHOLDS.get(current_phase)
        if min_messages is None or messages_total < min_messages:
            return  # Ещё рано

        recent = await get_recent_messages(telegram_id, limit=10)
        evaluation = await evaluate_phase(telegram_id, recent)
        # evaluation = PhaseEvaluation(recommendation="advance"|"stay", confidence=0.8, criteria_met=[...])

        if evaluation.recommendation == "advance" and evaluation.confidence >= 0.7:
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
                logger.info(f"Phase transition: {current_phase} → {next_phase} for {telegram_id}")

    except Exception as e:
        logger.warning(f"Phase check failed: {e}")
```

### `_extract_names(text: str) -> list[str]`
```
Regex: мо[йяиюей]\s+([А-ЯЁ][а-яё]{2,})
Стоп-лист: ["Бог", "Господь", "Инстаграм", "Телеграм", "Россия", "Москва", "Питер", ...]
Возвращает: ["Саша", "Настя"] (без дублей)
```

### `_extract_commitments(text: str) -> list[str]`
```
Regex: (завтра|на этой неделе|обещаю|попробую|планирую|решила)\s+(.+?)(?:\.|$)
Возвращает: ["поговорю с мамой", "начну ходить в зал"]
```

### `_extract_age(text: str) -> int | None`
```
Regex: мне\s+(\d{2})\s+(год|лет|года)
Возвращает: 32 или None
Валидация: 14 <= age <= 100
```

### `_extract_emotions(text: str) -> list[str]`
```
Словарь:
  "злость": ["бешу", "злюсь", "бесит", "взбесил", "раздражает"]
  "грусть": ["грустно", "тоскливо", "плачу", "слёзы"]
  "радость": ["радость", "счастлива", "кайф", "ура"]
  "тревога": ["волнуюсь", "страшно", "боюсь", "паника"]
  "усталость": ["устала", "выгорела", "сил нет", "замучена"]
Возвращает: ["злость", "усталость"]
```

### `_calc_pause_minutes(last_message_at: str) -> int`
```
Вход: ISO timestamp
Выход: количество минут с последнего сообщения
```

### `_get_next_phase(current: str) -> str | None`
```
PHASE_ORDER = ["ЗНАКОМСТВО", "ЗЕРКАЛО", "НАСТРОЙКА", "ПОРТРЕТ", "ЦЕЛЬ", "РИТМ"]
Возвращает следующую фазу или None (если РИТМ)
```

### `_now() -> str`
```
Возвращает: datetime.now(UTC).isoformat()
```

## CRUD из database.py, которые используются

| Функция | Шаг | Для чего |
|---------|-----|---------|
| `is_message_processed(message_id)` | 2 | Idempotency check |
| `mark_message_processed(message_id, telegram_id)` | 8 | Пометить обработанным |
| `get_user(telegram_id)` | 4 | Данные пользователя |
| `create_user(telegram_id, name)` | 4 | Создать нового |
| `add_message(telegram_id, role, content, ...)` | 8, 11 | Сохранить сообщение |
| `get_recent_messages(telegram_id, limit)` | 10, 13 | Последние 20 сообщений |
| `update_user(telegram_id, ...)` | 14 | Счётчики, фаза |
| `add_pending_fact(telegram_id, type, content, confidence)` | 12 | Мини-обновление |
| `add_emotion(telegram_id, emotion)` | 12 | Эмоции |
| `add_phase_transition(...)` | 13 | Лог переходов |

## Примеры вызовов зависимостей

### call_claude (шаг 10)
```python
response = await call_claude(
    messages=[
        {"role": "user", "content": "Привет, меня зовут Маша"},
        {"role": "assistant", "content": "Привет, Маша! Рада познакомиться..."},
        {"role": "user", "content": "Сегодня поругалась с мамой"},
    ],
    system="Ты — Ева, тёплая мудрая подруга...\n\n## ФАЗА: ЗНАКОМСТВО\n...",
    max_tokens=500,
    timeout=30,
)
# response → "Звучит, как будто это было непросто..."
```

### build_context (шаг 9)
```python
system_prompt, token_count, meta = await build_context(
    telegram_id=123456,
    current_message="Сегодня поругалась с мамой",
)
# system_prompt → "Ты — Ева...\n\n=== ПРОФИЛЬ ===\nМаша, 32...\n..."
# token_count → 3200
# meta.filled_vars → ["phase", "profile", "procedural", "episodes"]
```

### detect_crisis (шаг 6)
```python
crisis = detect_crisis("Хочу умереть")
# crisis → {"level": 3, "trigger": "хочу умереть", "is_verified": True}

crisis = detect_crisis("Умираю от смеха")
# crisis → {"level": 0, "trigger": None, "is_verified": True}
# (LLM-верификация определила false positive)
```

### evaluate_phase (шаг 13)
```python
evaluation = await evaluate_phase(telegram_id=123456, messages=recent_10)
# evaluation → PhaseEvaluation(recommendation="advance", confidence=0.85, criteria_met=["доверие установлено", "имя названо"])
```

### alerter.check (шаги 6, 9, 10, 11)
```python
await alerter.check(telegram_id=123456, event="crisis_level_3")
await alerter.check(telegram_id=123456, event="consecutive_empty_context")
await alerter.check(telegram_id=123456, event="consecutive_errors", value=3)
await alerter.check(telegram_id=123456, event="latency_critical_ms", value=28000)
```

### transcribe_voice (шаг 5)
```python
text = await transcribe_voice(voice_file_id="AwACAgIAAxkBAAI...")
# text → "Сегодня поругалась с мамой"
# Timeout: 30 сек, лимит аудио: 3 мин
```

## Edge cases

1. **Дубль сообщения (idempotency):** `is_message_processed` → True → return None. Обработка не выполняется.

2. **Два сообщения одновременно (мьютекс):** Второе ждёт release первого Lock. Порядок гарантирован для одного пользователя.

3. **Кризис уровня 3 (суицид):** Claude НЕ вызывается. Шаблонный ответ + контакты + alert владельцу. Всё за ~100ms.

4. **Голосовое > 3 мин:** transcribe_voice обрезает до 3 мин. Если timeout — fallback текстом.

5. **Claude timeout (30 сек):** 1 retry (встроен в call_claude) → если всё равно ошибка → FALLBACK_RESPONSE. Счётчик ошибок++.

6. **5 ошибок подряд:** пауза не нужна (rate limit и так защищает), но alert отправляется при >= 3.

7. **Rate limit (60/мин):** вежливый отказ, без обработки. Счётчик in-memory, сбрасывается каждую минуту.

8. **Пустой контекст (build_context ошибка):** FALLBACK_RESPONSE + alert "consecutive_empty_context".

9. **Новый пользователь (нет в БД):** создаётся на шаге 4 через create_user. Фаза = ЗНАКОМСТВО.

10. **Пользователь пишет во время full_memory_update:** WAL mode обеспечивает параллельность. Мьютекс session_manager НЕ блокирует full_memory_update (разные механизмы).

## Что НЕ делать

- **НЕ вызывать Claude при crisis level 3.** Шаблонный ответ мгновенно.
- **НЕ блокировать ответ** мини-обновлением (asyncio.create_task, не await).
- **НЕ блокировать ответ** проверкой фазы (asyncio.create_task).
- **НЕ обрабатывать** сообщение повторно (idempotency).
- **НЕ использовать** gather для зависимых операций (шаги строго последовательные).
- **НЕ хранить** историю сообщений в памяти — всегда читать из БД.
- **НЕ глотать** ошибки молча — логировать + alerter при аномалиях.
- **НЕ откатывать** фазы назад. Только вперёд.

## Диаграмма потока

```
Сообщение → [2] Idempotency? ──YES──→ return None
                │ NO
                ↓
            [3] Lock user
                │
            [4] Get user + pause
                │
            [5] Voice? ──YES──→ Whisper → text
                │ NO              │ fail → "Напиши текстом?"
                ↓                 ↓
            [6] Crisis? ──L3──→ Шаблон + alert → return
                │ L0-L2
                ↓
            [7] Rate limit? ──OVER──→ "Подожди" → return
                │ OK
                ↓
            [8] Save message + mark processed
                │
            [9] Build context
                │ fail → FALLBACK_RESPONSE
                ↓
            [10] Call Claude ──fail──→ FALLBACK_RESPONSE
                │ OK
                ↓
            [11] Save response + measure latency
                │
            [12] ASYNC: mini memory update (regex)
            [13] ASYNC: phase check (if msg % 10)
                │
            [14] Update counters → return response
```
