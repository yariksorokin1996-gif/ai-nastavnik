# Спецификация: bot/memory/context_builder.py

## Назначение

Собирает контекстное окно для запроса к Claude из 8 переменных (профиль, эпизоды, процедурная память и т.д.). Контролирует бюджет 3800 токенов, обрезая компоненты по таблице приоритетов.

**Текущее состояние:** файл существует (13 строк), будет полностью переписан.

## Зависимости (6)

```python
from bot.memory.profile_manager import get_profile_as_text       # -> str (≤1000 tok)
from bot.memory.episode_manager import find_relevant_episodes     # -> list[Episode] (≤800 tok)
from bot.memory.procedural_memory import get_procedural_as_text   # -> str (≤300 tok)
from bot.prompts.system_prompt import build_system_prompt          # -> str (~1500 tok)
from bot.memory.database import get_user, get_patterns, get_active_goal, get_recent_messages
from shared.config import TOKEN_BUDGET_SOFT                        # = 3800
```

## Публичный API

### `build_context(telegram_id: int, current_message: str) -> tuple[str, int, ContextMeta]`

**Вход:**
- `telegram_id` — ID пользователя в Telegram
- `current_message` — текущее сообщение пользователя (нужно для поиска релевантных эпизодов)

**Выход:**
- `system_prompt: str` — собранный системный промпт для Claude (≤3800 токенов)
- `token_count: int` — количество токенов в промпте
- `meta: ContextMeta` — метаданные сборки

**Ошибки:**
- Не бросает исключений. При ошибке любого компонента — пропускает его (пустая переменная).
- Логирует `WARNING` при пропуске компонента.

**Пример вызова:**

```python
# В session_manager.py, шаг 9:
system_prompt, token_count, meta = await build_context(
    telegram_id=123456,
    current_message="Сегодня опять поругалась с мамой"
)

# system_prompt → строка ~3200 токенов для Claude
# token_count → 3200
# meta.filled_vars → ["phase", "profile", "procedural", "episodes", "patterns"]
# meta.was_truncated → False
```

```python
# Новый пользователь (пустая память):
system_prompt, token_count, meta = await build_context(
    telegram_id=999999,
    current_message="Привет"
)

# system_prompt → ~1550 токенов (base_prompt + фаза + fallback)
# meta.filled_vars → ["phase"]
# meta.was_truncated → False
```

```python
# Активный пользователь с обрезкой:
system_prompt, token_count, meta = await build_context(
    telegram_id=123456,
    current_message="Думаю бросить работу"
)

# token_count → 3780 (после обрезки)
# meta.was_truncated → True
# meta.truncated_vars → ["pause_context", "episodes"]
```

## Модель ContextMeta

```python
from pydantic import BaseModel

class ContextMeta(BaseModel):
    filled_vars: list[str]           # какие переменные заполнены (не пустые)
    tokens_per_var: dict[str, int]   # сколько токенов каждая заняла
    was_truncated: bool              # была ли обрезка
    truncated_vars: list[str]        # какие переменные обрезаны
```

## Алгоритм (пошагово)

### Шаг 1: Загрузить данные пользователя

```python
user = await get_user(telegram_id)
if not user:
    raise ValueError(f"User {telegram_id} not found")

current_phase = user.get("current_phase", "ЗНАКОМСТВО")
pause_minutes = _calc_pause(user.get("last_message_at"))
```

### Шаг 2: Собрать 8 переменных (параллельно где можно)

```python
# Параллельные запросы (независимые):
profile_text, procedural_text, episodes, patterns, goal = await asyncio.gather(
    _safe_call(get_profile_as_text, telegram_id),          # ≤1000 tok
    _safe_call(get_procedural_as_text, telegram_id),       # ≤300 tok
    _safe_call(find_relevant_episodes, telegram_id, current_message, limit=3),  # ≤800 tok
    _safe_call(get_patterns, telegram_id),                  # ≤200 tok
    _safe_call(get_active_goal, telegram_id),               # для commitments
)
```

`_safe_call` — обёртка try/except, при ошибке возвращает None + логирует WARNING.

### Шаг 3: Форматировать каждую переменную

```python
vars = {}
vars["system_prompt"] = build_system_prompt(current_phase)                # ~1500 tok, ВСЕГДА
vars["phase"] = f"## ТЕКУЩАЯ ФАЗА: {current_phase}\n{PHASE_DESCRIPTIONS[current_phase]}"  # ~50-100 tok

# Опциональные (None → пропускаем):
if profile_text:
    vars["profile"] = f"=== ПРОФИЛЬ ===\n{profile_text}"
else:
    vars["profile"] = "=== ПРОФИЛЬ ===\nНовый пользователь. Информации пока нет. Наблюдай."

if procedural_text:
    vars["procedural"] = f"=== КАК С НЕЙ РАБОТАТЬ ===\n{procedural_text}"
else:
    vars["procedural"] = "=== КАК С НЕЙ РАБОТАТЬ ===\nСтиль не определён. Наблюдай и подстраивайся."

if episodes:
    vars["episodes"] = _format_episodes(episodes)            # ≤800 tok

if patterns:
    vars["patterns"] = _format_patterns(patterns)            # ≤200 tok

if goal and goal.get("status") == "active":
    commitments = _format_commitments(goal)                  # ≤200 tok
    if commitments:
        vars["commitments"] = commitments

if pause_minutes and pause_minutes >= 60:
    vars["pause_context"] = _format_pause(pause_minutes, user)  # ≤100 tok
```

### Шаг 4: Подсчитать токены

```python
def _estimate_tokens(text: str) -> int:
    """Оценка токенов для русского текста: ~3.3 токена на слово."""
    words = len(text.split())
    return int(words * 3.3)
```

### Шаг 5: Обрезка если > 3800 токенов

Обрезка по приоритетам (первым режется наименее важное):

| Приоритет | Переменная | Полный лимит | Обрезанный лимит | Как режется |
|-----------|-----------|-------------|-----------------|-------------|
| 1 (первым) | pause_context | 100 tok | 0 | Удаляем целиком |
| 2 | commitments | 200 tok | ~100 tok | Только невыполненные обязательства |
| 3 | patterns | 200 tok | ~100 tok | ТОП-3 по частоте (count DESC) |
| 4 | episodes | 800 tok | 400 tok | 2 вместо 3 эпизодов |
| 5 | people (в профиле) | 300 tok | 150 tok | Только мама, муж/парень, дети |
| 6 | procedural | 300 tok | 150 tok | Только секция «что работает» |
| 7 | profile | 1000 tok | 700 tok | Убираем «стиль общения» |
| 8 (НИКОГДА) | system_prompt + phase | ~1600 tok | ~1600 tok | **НЕ РЕЖЕТСЯ** |

```python
total = sum(_estimate_tokens(v) for v in vars.values())
truncated_vars = []

if total > TOKEN_BUDGET_SOFT:
    for priority, var_name, truncate_fn in TRUNCATION_ORDER:
        if var_name in vars:
            old_tokens = _estimate_tokens(vars[var_name])
            vars[var_name] = truncate_fn(vars[var_name])
            new_tokens = _estimate_tokens(vars[var_name])
            if new_tokens < old_tokens:
                truncated_vars.append(var_name)
            total = sum(_estimate_tokens(v) for v in vars.values())
            if total <= TOKEN_BUDGET_SOFT:
                break
```

### Шаг 6: Собрать финальный промпт

```python
# Порядок сборки (важен для prompt caching):
parts = [
    vars["system_prompt"],      # 1. Базовый промпт (ВСЕГДА, не меняется → кэш)
    vars["phase"],              # 2. Фаза (редко меняется → кэш)
    vars.get("profile", ""),    # 3-9. Меняются часто
    vars.get("procedural", ""),
    vars.get("episodes", ""),
    vars.get("patterns", ""),
    vars.get("commitments", ""),
    vars.get("pause_context", ""),
]
system_prompt = "\n\n".join(p for p in parts if p)
```

### Шаг 7: Вернуть результат

```python
meta = ContextMeta(
    filled_vars=[k for k, v in vars.items() if v],
    tokens_per_var={k: _estimate_tokens(v) for k, v in vars.items() if v},
    was_truncated=bool(truncated_vars),
    truncated_vars=truncated_vars,
)
return system_prompt, _estimate_tokens(system_prompt), meta
```

## Внутренние функции

### `_format_episodes(episodes: list[dict]) -> str`
```
Вход: список Episode (id, title, summary, emotional_tone)
Выход: "=== КОНТЕКСТ ПРОШЛЫХ РАЗГОВОРОВ ===\n[15.01] Конфликт с клиентом (тревога → облегчение)\nКонспект...\n\n[12.01] ..."
Лимит: ≤800 токенов (2-3 эпизода)
```

### `_format_patterns(patterns: list[dict]) -> str`
```
Вход: список Pattern (pattern_type, pattern_text, count)
Выход: "=== ПАТТЕРНЫ ===\n• Избегание (×5): откладывает решения\n• ..."
Сортировка: count DESC, лимит ≤200 токенов
```

### `_format_commitments(goal: dict) -> str`
```
Вход: Goal с goal_steps
Выход: "=== ТЕКУЩАЯ ЦЕЛЬ ===\n«Поговорить с мамой»\n☐ Написать в WhatsApp (сегодня)\n☐ ..."
Показывать: только невыполненные (status = "pending")
```

### `_format_pause(pause_minutes: int, user: dict) -> str`
```
Вход: минуты паузы, данные пользователя
Выход: "⏸ Пауза 3 часа. Последняя тема: конфликт с мамой."
Только если pause_minutes >= 60
```

### `_calc_pause(last_message_at: str | None) -> int | None`
```
Вход: ISO timestamp последнего сообщения
Выход: количество минут паузы или None
```

### `_safe_call(fn, *args) -> Any | None`
```
try/except обёртка. При ошибке: logger.warning(f"...: {e}"), return None
```

## CRUD из database.py, которые используются

| Функция | Для чего |
|---------|---------|
| `get_user(telegram_id)` | current_phase, last_message_at |
| `get_patterns(telegram_id)` | паттерны для контекста |
| `get_active_goal(telegram_id)` | текущая цель + шаги |
| `get_goal_steps(goal_id)` | шаги цели (для commitments) |

## Edge cases

1. **Новый пользователь (пустая память):** profile = fallback, procedural = fallback, episodes = [], patterns = []. Результат: ~1550 токенов (base_prompt + phase + fallback).

2. **0 эпизодов:** переменная episodes пропускается. Нет ошибки.

3. **Токен-бюджет после полной обрезки всё ещё превышен:** теоретически невозможно (base_prompt + phase = ~1600, а бюджет 3800). Если всё же произойдёт — `logger.error`, вернуть только base_prompt + phase.

4. **database.get_user вернул None:** raise ValueError (пользователь должен существовать на этом этапе).

5. **Ошибка LLM в find_relevant_episodes:** _safe_call вернёт None → episodes пропускаются → лог WARNING.

6. **Все компоненты памяти пустые (кроме base):** нормальная ситуация для нового пользователя.

## Что НЕ делать

- **НЕ резать system_prompt и phase** — это приоритет 8, никогда не обрезается.
- **НЕ вызывать LLM** — context_builder только собирает, LLM-вызовы делают зависимости (find_relevant_episodes).
- **НЕ кэшировать** профиль/эпизоды между вызовами — данные могут измениться.
- **НЕ менять порядок сборки** — base_prompt первым для prompt caching.
- **НЕ блокировать** при ошибках зависимостей — _safe_call + fallback.

## Бюджет токенов (справка)

| Компонент | Новый юзер | Средний | Активный |
|-----------|-----------|---------|----------|
| system_prompt | 1500 | 1500 | 1500 |
| phase | 50 | 100 | 100 |
| profile | 0 (fallback ~50) | 500 | 900 |
| procedural | 0 (fallback ~30) | 150 | 250 |
| episodes | 0 | 400 | 700 |
| patterns | 0 | 100 | 180 |
| commitments | 0 | 80 | 150 |
| pause_context | 0 | 50 | 80 |
| **ИТОГО** | **~1630** | **~2880** | **~3860** |
