# Архитектура команды AI-агентов для проекта Ева v2.2

> Обновлён 2026-03-03. 3 раунда критики (14 проблем) + feedback loop + закрытие 12 дыр из критического анализа.

## Контекст

Проект Ева — 23 шага от планирования до запуска. Один контекст не вместит весь проект. Решение: Lead-агент (Opus) координирует специализированных субагентов через **встроенный механизм Claude Code** — файлы `.claude/agents/*.md` с YAML frontmatter.

Каждый агент:
- Имеет свой набор инструментов (allowlist в YAML)
- Работает на указанной модели (sonnet/haiku)
- Имеет персистентную память между вызовами (`.claude/agent-memory/<name>/MEMORY.md`)
- Запускается автоматически (по description) или явно (по имени)
- Может быть возобновлён (`resume`) для продолжения работы с полным контекстом

Паттерны:
- Orchestrator-Workers (декомпозиция и параллелизация)
- Context Engineering (файлы = долгосрочная память, контекст = оперативка)
- Feedback Loop (ошибки → анализ → коррекция промптов)

---

## 1. СОСТАВ КОМАНДЫ

### Lead (основная сессия Claude Code)

| | |
|---|---|
| Модель | Opus 4.6 |
| Инструменты | Все |
| Memory | `~/.claude/projects/*/memory/` (auto memory, первые 200 строк) |
| Роль | Координатор, архитектор, ревьюер |

**Что делает:**
- Читает STATE.md и tasks.json при старте сессии
- Декомпозирует текущий шаг на задачи
- Пишет контракты (Pydantic модели + сигнатуры) → сохраняет в tasks.json
- Запускает субагентов (параллельно где возможно)
- Ревьюит результаты (читает написанный код)
- Запускает тесты
- Коммитит + обновляет STATE.md
- Принимает архитектурные решения
- Пишет документацию напрямую (шаги 1-4)
- Проводит ретроспективу (feedback loop, секция 8)
- Спрашивает пользователя при неясности

**Чего НЕ делает:**
- Не пишет большие модули сам (делегирует coder-backend/frontend)
- Не пишет тесты сам (делегирует tester)

---

### Субагент 1: coder-backend

Файл: `.claude/agents/coder-backend.md`

```markdown
---
name: coder-backend
description: "Python-разработчик проекта Ева. Writes backend code: bot modules, memory system, handlers, API endpoints. Use when implementing a new Python module or modifying existing backend code."
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
permissionMode: acceptEdits
memory: project
maxTurns: 25
---

Ты — Python-разработчик проекта Ева (Telegram-бот).

## Правила

- Пишешь ТОЛЬКО код, который тебе поручили. Не трогай другие файлы
- Следуй контракту (Pydantic модель + сигнатура). Если контракт неудобен — НЕ меняй сам, опиши в заметках что не так
- async def для всех IO-операций
- aiosqlite для БД, httpx для HTTP
- Конкретные except + конкретная реакция. Не except Exception
- Timeout на каждый внешний вызов
- logging, не print
- Pydantic на границах (вход/выход)
- Нет hardcode — всё из shared/config.py
- Запусти `ruff check` перед завершением

## Память

Обнови свою память (MEMORY.md) ТОЛЬКО если:
- Нашёл неочевидный паттерн или gotcha
- Принял решение, которое повлияет на будущие модули
- Обнаружил ограничение библиотеки/фреймворка
НЕ записывай рутину («написал модуль X», «использовал aiosqlite»)

## Уроки из ошибок

(Эта секция обновляется Lead'ом по результатам ретроспектив. Лимит: 10 записей.)

## Формат ответа

В конце ОБЯЗАТЕЛЬНО:

### Результат
- Создано: [список файлов]
- Изменено: [список файлов]
- ruff check: ✅/❌

### Заметки
- [Что было непонятно в контракте]
- [Какие решения принял сам]
- [Что требует внимания Lead'а]
```

---

### Субагент 2: coder-frontend

Файл: `.claude/agents/coder-frontend.md`

```markdown
---
name: coder-frontend
description: "Фронтенд-разработчик. Writes React/TypeScript code for Telegram Mini App. Use when implementing new webapp pages, components, or modifying existing frontend code."
tools: Read, Write, Edit, Grep, Glob, Bash
model: sonnet
permissionMode: acceptEdits
memory: project
maxTurns: 25
---

Ты — фронтенд-разработчик проекта Ева (Telegram Mini App).

## Стек
React 19 + Vite + TypeScript + @telegram-apps/telegram-ui v2.1.13 + lucide-react

## Правила

- Следуй макетам из docs/06_webapp_mockups.md
- Используй компоненты из telegram-ui (AppRoot, Section, Cell, Button, Avatar, Tabbar)
- API-клиент: webapp/src/api.ts. Добавляй методы туда
- Стили: Apple Health / iOS Settings. Палитра: #FF6B8A акцент, #F2F2F7 фон
- Контраст текста: #D4466A (WCAG AA)
- Тёмная тема: CSS-переменные, AppRoot appearance={colorScheme}
- Avatar sizes: только 20|24|28|40|48|96
- Authorization: `tma ${initData}` header
- TypeScript strict: никаких any
- Deep link «Написать Еве»: `Telegram.WebApp.openTelegramLink('https://t.me/${VITE_BOT_USERNAME}')`
- Запусти `cd webapp && npx tsc --noEmit` перед завершением

## Память

Обнови MEMORY.md ТОЛЬКО если нашёл неочевидный паттерн, gotcha в telegram-ui, или ограничение.

## Уроки из ошибок

(Обновляется Lead'ом. Лимит: 10 записей.)

## Формат ответа

В конце ОБЯЗАТЕЛЬНО:

### Результат
- Создано: [список файлов]
- Изменено: [список файлов]

### Заметки
- [Что проверить визуально]
- [Какие решения принял сам]
```

---

### Субагент 3: tester

Файл: `.claude/agents/tester.md`

```markdown
---
name: tester
description: "Тестировщик. Writes and runs pytest tests for Python modules. Use after a module is implemented to create unit, integration, and E2E tests."
tools: Read, Write, Edit, Bash, Grep, Glob
model: sonnet
permissionMode: acceptEdits
memory: project
maxTurns: 25
---

Ты — тестировщик проекта Ева.

## Правила

- pytest + pytest-asyncio + pytest-cov
- Для каждого модуля: минимум 3 теста (happy path, edge case, error case)
- LLM-вызовы ВСЕГДА мокаются (unittest.mock.AsyncMock)
- Фикстуры в conftest.py, не хардкод в тестах
- Покрытие >= 80% line coverage для каждого модуля
- Запусти pytest ПОСЛЕ написания тестов. Если красный — исправь тест ИЛИ сообщи о баге в коде
- Не меняй продакшн-код. Только тесты
- ВАЖНО: тестируй по КОНТРАКТУ (что ДОЛЖНО работать), а не по реализации (что СЕЙЧАС работает). Контракт будет в промпте от Lead'а

## Память

Обнови MEMORY.md ТОЛЬКО если: нашёл рабочий паттерн мока, обнаружил ограничение pytest, или нашёл неочевидный баг.

## Уроки из ошибок

(Обновляется Lead'ом. Лимит: 10 записей.)

## Формат ответа

В конце ОБЯЗАТЕЛЬНО:

### Результат
- Создано: [список файлов]
- pytest: ✅/❌ (X passed, Y failed)
- Coverage: X%

### Заметки
- [Баги в продакшн-коде, если нашёл]
- [Что не удалось протестировать и почему]
```

---

### Субагент 4: critic

Файл: `.claude/agents/critic.md`

| | |
|---|---|
| Модель | Sonnet |
| Инструменты | Read, Grep, Glob, Bash |
| Memory | `.claude/agent-memory/critic/MEMORY.md` |
| Роль | Критик-ревьюер (read-only) |
| maxTurns | 15 |

**Что делает:**
- Проверяет планы/контракты ПЕРЕД делегацией (чеклисты А + А2)
- Проверяет код + тесты ПОСЛЕ реализации (чеклисты Б + В)
- Выдаёт вердикт: PASS / FIX NEEDED / REWRITE с приоритетами P0/P1/P2

**Чего НЕ делает:**
- Не правит код, документы, тесты
- Не предлагает рефакторинг или стилистические правки

**5 чеклистов:**
- **А** — план/контракт (полнота, edge cases, fallback)
- **А2** — целостность документации (перекрёстная проверка spec vs код vs модели)
- **Б** — код (сигнатуры, параметры, except, timeout, hardcode)
- **В** — тесты (покрытие, ветки, edge cases, моки)
- **Г** — документация/specs (поля, схемы, примеры)
- **Д** — user experience (сценарии из контракта → fallback, полнота, пауза)

---

### Исследование — без постоянного агента

Для исследования — встроенный `Explore` (оптимизирован для навигации по коду) или ad-hoc `general-purpose` с WebSearch.

---

## 2. СТРУКТУРА ПАПОК

```
ai_nastavnik/
├── .claude/
│   ├── agents/                          # Определения субагентов (YAML frontmatter)
│   │   ├── coder-backend.md
│   │   ├── coder-frontend.md
│   │   ├── tester.md
│   │   └── critic.md
│   │
│   ├── agent-memory/                    # Персистентная память субагентов (в git)
│   │   ├── coder-backend/
│   │   │   └── MEMORY.md
│   │   ├── coder-frontend/
│   │   │   └── MEMORY.md
│   │   ├── tester/
│   │   │   └── MEMORY.md
│   │   └── critic/
│   │       └── MEMORY.md
│   │
│   └── CLAUDE.md                        # Правила проекта (переживает compaction)
│
├── .state/                              # Состояние проекта (в git)
│   └── tasks.json                       # Задачи + контекст + лог ошибок
│
├── STATE.md                             # Человекочитаемое состояние
├── docs/
├── bot/
├── webapp/
└── tests/                               # Тесты (вместо test_*.py в корне)
    ├── conftest.py
    ├── fixtures/
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## 3. УПРАВЛЕНИЕ СОСТОЯНИЕМ (2 файла)

### 3.1. STATE.md (для человека)

Обновляется Lead'ом. Формат без изменений.

### 3.2. tasks.json (source of truth)

**При конфликте между STATE.md и tasks.json → tasks.json побеждает.** STATE.md — производная, tasks.json — первоисточник.

```json
{
  "version": "2.1",
  "current": [
    {
      "task": "8.2",
      "status": "in_progress",
      "agent_id": null,
      "context": {
        "contract": "async def migrate(db: aiosqlite.Connection) -> None: ...",
        "decisions": ["WAL mode", "Идемпотентная миграция"],
        "blockers": []
      }
    }
  ],
  "steps": [
    {
      "step": 8,
      "name": "Собрать ядро памяти",
      "output": "bot/memory/",
      "done": false,
      "tasks": [
        {
          "id": "8.1",
          "description": "Pydantic модели",
          "agent": "coder-backend",
          "files": ["shared/models.py"],
          "contract": "class SemanticProfile(BaseModel): name: str; ...",
          "depends_on": [],
          "done": true,
          "completed_at": "2026-03-05"
        },
        {
          "id": "8.2",
          "description": "Миграция БД",
          "agent": "coder-backend",
          "files": ["bot/memory/database.py"],
          "contract": "async def migrate(db) -> None: 7 таблиц, IF NOT EXISTS",
          "depends_on": ["8.1"],
          "done": false
        }
      ]
    }
  ],
  "log": [
    "2026-03-05 | 8.1 | coder-backend | shared/models.py | done, 12 моделей",
    "2026-03-05 | 8.2 | coder-backend | ERROR | missing_timeout | httpx.get без timeout"
  ],
  "errors_since_retro": 0,
  "last_retro": "2026-03-05"
}
```

**Ключевые изменения vs v2:**
- `current` — **массив** (поддержка параллельных задач)
- `contract` — поле в каждой задаче (контракт хранится, не теряется)
- `agent_id` — для `resume` (продолжение работы агента)
- `errors_since_retro` — счётчик для feedback loop
- Завершённые шаги: **архивируются** (Lead убирает `tasks` у done-шагов, оставляя только `step/name/done/completed_at`). Это не даёт файлу раздуваться

---

## 4. ПРОТОКОЛ СЕССИИ

### 4.1. Startup (4 шага)

```
1. Прочитать STATE.md + .state/tasks.json     → где мы, что делаем
2. git status && git log --oneline -3          → состояние репо
3. pytest tests/ -x --tb=line -q               → все тесты зелёные? (5 сек)
4. Взять задачу: tasks.json → current          → начать работу
```

Если шаг 3 красный → чинить ПЕРЕД новой работой.

### 4.2. Рабочий цикл (6 шагов с критиком)

```
Lead:
  1. Берёт задачу из tasks.json → обновляет current
  2. Для документации (шаги 1-4): пишет НАПРЯМУЮ
  3. Для кода:
     a. Пишет контракт → сохраняет в tasks.json (поле contract)
     b. CRITIC-1 (план): проверяет контракт + docs (чеклисты А + А2)
        → PASS → шаг c / FIX NEEDED → Lead правит контракт, повтор b
     c. Формирует промпт: контракт + входные файлы + антипаттерны + DoD
     d. Запускает coder-backend/frontend
     e. Получает результат → Read файлов
     f. tester: тесты (ВКЛЮЧАЯ контракт в промпте!)
     g. CRITIC-2 (результат): проверяет код + тесты (чеклисты Б + В)
        → PASS → шаг h
        → FIX NEEDED:
          g1. ЗАПИСАТЬ каждый P0/P1 в tasks.json log (date, task_id, agent, tag, description)
          g2. errors_since_retro += кол-во P0/P1
          g3. Исправить: P0 → обязателен (resume coder/tester), P1 → если быстро, P2 → пропустить
          g4. errors_since_retro >= 3? → РЕТРОСПЕКТИВА (секция 8.2) → errors_since_retro = 0
          g5. ПОКАЗАТЬ пользователю таблицу отчёта (формат в CLAUDE.md ## Отчёт после критика)
     g-bis. «Глазами пользователя» (если задача user-facing): Lead прогоняет
            сценарии из контракта через финальный код. Сломанный = FIX NEEDED.
     h. pytest → зелёный?
        - Да → tasks.json done:true + git commit
        - Нет → resume агента с ошибкой (до 3 попыток)
  4. Следующая задача
```

**Когда НЕ запускать критика:**
- Правка < 10 строк (typo, rename)
- Hotfix (сначала чиним, потом ревьюим)

**Когда CRITIC-1 (план) не нужен:**
- Контракт не менялся с прошлой проверки
- Контракт скопирован из проверенного spec-файла

**Когда запускать критика дважды на результат:**
- Сложные модули (много зависимостей)
- Границы системы (API, безопасность)

### 4.3. End Ritual

```
1. git status → всё закоммичено?
2. pytest → всё зелёное?
3. Обновить STATE.md
4. Обновить tasks.json (current, архивировать done-шаги)
5. git commit "session end: обновлён STATE.md"
```

---

## 5. КОНТРАКТЫ

### 5.1. Где хранятся

В tasks.json, поле `contract` у каждой задачи. Переживает compaction, доступен для tester'а.

### 5.2. Spec-файлы для сложных модулей

Для модулей с **5+ зависимостями** Lead создаёт `specs/<module>_spec.md` перед запуском агента.

Spec содержит:
- Полный алгоритм (шаг за шагом)
- ВСЕ зависимости с примерами вызовов (не только сигнатуры)
- Edge cases и fallback
- Что НЕ делать

Модули, требующие spec: `session_manager.py`, `context_builder.py`, `full_memory_update` (job).

### 5.3. Мягкие контракты, с правом на изменение

```
1. Lead пишет контракт v1 → tasks.json
2. coder-backend реализует
3. Если контракт неудобен:
   - Субагент НЕ меняет сам — описывает в «Заметках»
   - Lead решает: контракт v2 (обновить в tasks.json) или настоять на v1
   - Изменение = запись в log
```

### 5.4. Сценарии в контракте

Для задач с тегом `user-facing` лид добавляет секцию «Сценарии» в контракт.
Персоны берутся из `docs/user_scenarios.md` и адаптируются под конкретный модуль:

```
Сценарии:
1. [Новый]: вход=[конкретные данные] → выход=[что ожидаем] → чеклист=[что проверить]
2. [Активный]: вход=[...] → выход=[...] → чеклист=[...]
3. [Вернувшийся]: вход=[...] → выход=[...] → чеклист=[...]
```

Кодер проходит каждый. Тестер пишет тест на каждый. Критик проверяет каждый.

### 5.5. Правило задачи — гибкое

Один субагент = один логический модуль. Может быть 1 файл, может 5. Критерий: модуль можно протестировать изолированно.

---

## 6. ПАРАЛЛЕЛИЗАЦИЯ

### Когда параллельно

**Да:**
- coder-backend (модуль A) + coder-frontend (экран B, если API готов)
- coder-backend (модуль A) + tester (тесты модуля B, уже готового)
- Два независимых модуля бэкенда (разные файлы)

**Нет:**
- Два субагента пишут в один файл
- coder-backend + tester для ОДНОГО модуля
- Модуль, зависящий от ещё не написанного

### Честные ограничения

Параллельные субагенты экономят **контекст Lead'а**, но Lead ревьюит результаты последовательно. ~1.3x, не 2x.

При параллельной работе: `current` — массив из 2 элементов, каждый со своим `agent_id`.

---

## 7. СТРАТЕГИЯ COMPACTION

### Что переживает

| Источник | Переживает? | Действие |
|----------|------------|----------|
| `.claude/CLAUDE.md` | ✅ Автоматически | Критичные правила — сюда |
| Auto memory (MEMORY.md) | ✅ Автоматически (200 строк) | Архитектурные решения — сюда |
| STATE.md | ❌ Файл на диске | Перечитать |
| tasks.json | ❌ Файл на диске | Перечитать (current = контекст) |
| Обсуждения в чате | ❌ Сжимаются | Важное → записать в файл ДО |

### Протокол восстановления

```
1. .claude/CLAUDE.md           → правила (автоматически)
2. MEMORY.md                   → контекст (автоматически)
3. STATE.md                    → где мы
4. .state/tasks.json           → current + contract + context
5. git log --oneline -3        → последние изменения
6. Файлы текущего модуля       → контекст кода
```

### Правило «записывай сразу»

Принял решение → **сразу** в STATE.md или tasks.json. Compaction может случиться в любой момент.

---

## 8. FEEDBACK LOOP (самообучение команды)

### 8.1. Запись ошибок

При каждом ревью, если Lead нашёл ошибку в коде агента:

```
# В tasks.json log:
"2026-03-05 | 8.2 | coder-backend | ERROR | missing_timeout | httpx.get без timeout"
```

Формат: `дата | задача | агент | ERROR | тип_ошибки | описание`

`errors_since_retro` += 1

### 8.2. Ретроспектива (триггер: >= 3 ошибок)

Когда `errors_since_retro >= 3`, Lead проводит мини-анализ:

```
1. Прочитать все ERROR из log с последней ретроспективы
2. Есть ли повторяющийся тип? (>= 2 одинаковых у одного агента)
   - Да → это промпт не покрывает → добавить в «Уроки» агента
   - Нет → разовые ошибки, игнорировать
3. Прочитать agent-memory каждого агента:
   - Есть ли неправильные записи? → удалить
   - Есть ли ценные паттерны? → оставить
4. errors_since_retro = 0, last_retro = сегодня
5. Записать в log: "RETRO | что нашли | что исправили"
```

### 8.3. Коррекция промптов агентов

Секция `## Уроки из ошибок` в каждом `.claude/agents/<name>.md`:

```markdown
## Уроки из ошибок

1. ОБЯЗАТЕЛЬНО: timeout=30 на каждый httpx вызов (ретро 2026-03-05)
2. НЕ использовать cursor.execute напрямую, только async with db.execute() (ретро 2026-03-06)
```

**Правила:**
- Лимит: 10 записей (самые старые/неактуальные вычищаются)
- Формат: конкретное правило + дата ретроспективы
- Только Lead правит эту секцию (агент не трогает)

### 8.4. Эскалация (два шанса)

```
Ошибка повторилась:
  1-й раз → правило в «Уроки» промпта агента
  2-й раз → правило в agent-memory/MEMORY.md (жёсткое ограничение)
  3-й раз → это ограничение модели. Lead добавляет в свой чеклист ревью
```

### 8.5. Ревью agent-memory (каждые 5 задач)

Lead читает `.claude/agent-memory/<agent>/MEMORY.md` для каждого активного агента:
- Неправильные записи → удалить
- Шум (рутинные записи) → удалить
- Ценные паттерны → оставить

---

## 9. ЦИКЛЫ ИТЕРАЦИЙ

### 9.1. Цикл модуля

```
Lead: контракт → tasks.json (поле contract)
  ↓
CRITIC-1: проверяет контракт (чеклисты А + А2)
  → PASS → продолжаем / FIX NEEDED → Lead правит
  ↓
coder-backend: реализация
  ↓
tester: тесты (КОНТРАКТ включён в промпт!)
  ↓
CRITIC-2: проверяет код + тесты (чеклисты Б + В)
  → PASS → продолжаем
  → FIX NEEDED:
      g1. ЗАПИСАТЬ P0/P1 в tasks.json log
      g2. errors_since_retro += кол-во P0/P1
      g3. Исправить (P0 обязательно, P1 если быстро, P2 пропустить)
      g4. errors_since_retro >= 3? → РЕТРОСПЕКТИВА
      g5. ПОКАЗАТЬ пользователю таблицу отчёта
  ↓
Lead: pytest → зелёный?
  ├── Да → commit + done:true
  └── Нет → resume coder-backend (макс 3 попытки)
                └── 3 попытки → Lead чинит сам или спрашивает
```

### 9.2. Цикл интеграции (каждые 2-3 модуля)

```
Модуль A + Модуль B готовы → интеграционный тест → зелёный? → продолжаем
```

### 9.3. Цикл шага (один из 23)

```
Начало:
  1. Lead читает plan.md → секцию шага
  2. Декомпозирует → tasks.json (задачи + контракты)
  3. Определяет порядок (depends_on)

Работа:
  4. Для каждой задачи: цикл модуля (9.1)
  5. После всех задач: интеграционный тест (9.2)

Завершение:
  6. Все задачи done:true + все тесты зелёные
  7. STATE.md обновлён
  8. git commit "step N complete"
  9. Проверить Definition of Done из plan.md
  10. Архивировать done-шаг в tasks.json (убрать tasks, оставить step/name/done)
```

### 9.4. Правило 3 попыток

При ошибке → `resume` агента (не новый вызов). Агент помнит контекст.

3 попытки без результата:
1. Lead читает код и ошибку сам
2. Понимает → чинит или даёт ТОЧНУЮ инструкцию
3. Не понимает → спрашивает пользователя

### 9.5. Resume vs новый вызов

| Ситуация | Что делать |
|----------|-----------|
| Тесты красные, нужно починить | `resume` (контекст сохранён) |
| Контракт изменился, нужно переделать | Новый вызов (старый контекст неактуален) |
| Новая задача | Новый вызов |
| Ревью: мелкие замечания | `resume` |

---

## 10. ОБРАБОТКА ОШИБОК

### 10.1. Субагент вернул невалидный код

```
Lead: Read файл → конкретная проблема → resume агента с цитатой + объяснением
```

### 10.2. Тесты падают после изменений

```
Lead: git diff → баг в новом коде или тест устарел →
      resume coder-backend или tester соответственно
```

### 10.3. Конфликт контрактов

```
Lead: прочитать ОБА модуля → найти стык →
      исправить контракт v2 ИЛИ код
```

### 10.4. Сессия прервалась

```
Новая сессия → startup (4 шага) → git status →
  Незакоммиченные? → оценить: рабочие? → commit / stash
  Нет → продолжить с tasks.json current
```

### 10.5. Rollback шага

```
git log → найти коммит начала шага
git revert <commit>..HEAD --no-commit && git commit -m "rollback step N: причина"
tasks.json → задачи шага done:false
STATE.md → записать причину
```

### 10.6. Known limitations

| Проблема | Статус | Mitigation |
|----------|--------|------------|
| coder-frontend: TypeScript | Решено | Node.js установлен, `npx tsc --noEmit` перед завершением |
| Agent memory может содержать ошибки | Решено | Ревью каждые 5 задач (секция 8.5) |
| Модель может игнорировать правила промпта | Принято | Эскалация: промпт → memory → чеклист ревью |

---

## 11. CLAUDE.md ПРОЕКТА

Файл: `.claude/CLAUDE.md` (переживает compaction)

```markdown
# Ева — Telegram-бот

## Команды
- Тесты: pytest tests/ -v --cov=bot --cov-report=term-missing
- Линтер: ruff check bot/ shared/ backend/
- Быстрая проверка: pytest tests/ -x --tb=line -q
- Проверка TypeScript: cd webapp && npx tsc --noEmit

## Архитектура
- Бот: aiogram 3.x, БД: SQLite + aiosqlite + WAL mode
- API: FastAPI (backend/api.py)
- Webapp: React 19 + Vite + TS (webapp/)
- LLM диалог: Claude Sonnet 4.5, LLM фоновое: GPT-4o-mini

## Ключевые правила
- Фазы ТОЛЬКО вперёд (6 штук)
- Токен-бюджет: 3800 мягкий лимит
- Карта людей в profile_json.people, НЕ отдельная таблица
- Мини-обновление памяти: regex (НЕ LLM)
- Полное обновление: при паузе >= 30 мин

## Субагенты
- coder-backend: Python (Sonnet, acceptEdits, maxTurns 25)
- coder-frontend: React/TS (Sonnet, acceptEdits, maxTurns 25)
- tester: pytest (Sonnet, acceptEdits, maxTurns 25)
- Исследование: встроенный Explore

## Источники правды
- tasks.json = задачи и контракты (побеждает при конфликте с STATE.md)
- STATE.md = человекочитаемая сводка
- docs/plan.md = ТЗ проекта (v5.2)
- docs/agplan.md = протокол работы команды агентов
```

---

## 12. ПОРЯДОК РЕАЛИЗАЦИИ

### Сессия 0: Инфраструктура агентов

1. Создать `.claude/agents/` с 3 файлами
2. Создать `.claude/agent-memory/` с пустыми MEMORY.md
3. Создать `.claude/CLAUDE.md`
4. Создать `.state/tasks.json` (шаги 1-23, задачи шагов 1-4)
5. Создать `tests/` структуру + `conftest.py`
6. **Аудит** `test_critical.py` (1453 строки) — что переиспользовать, что удалить
7. Перенести живые тесты в `tests/`, удалить мёртвые
8. Обновить STATE.md
9. git commit

### Сессия 1-4: Документация (Lead напрямую)

| Сессия | Документ | Агенты |
|--------|----------|--------|
| 1 | `docs/03_phases.md` | Lead |
| 2 | `docs/04_dialog_engine.md` | Lead |
| 3 | `docs/05_test_scenarios.md` | Lead |
| 4 | `docs/06_webapp_mockups.md` → **ПЛАНИРОВАНИЕ ЗАВЕРШЕНО** | Lead |

### Сессия 5+: Код (субагенты вступают)

Начиная с шага 5: coder-backend, tester, coder-frontend.

---

## 13. ОДНА СЕССИЯ ≈ ОДИН ШАГ

| Тип шага | Объём | Сессий | Агенты |
|----------|-------|--------|--------|
| Документация (1-4) | ~3000 слов | 1 | Lead |
| Модели/миграция (5-8) | 2-4 модуля + тесты | 1-2 | coder-backend + tester |
| Движок (9) | 1 большой модуль | 1-2 | coder-backend + tester |
| Обработчики (10-11) | 2-3 файла | 1 | coder-backend + tester |
| Webapp (12-16) | 1 экран | 1 | coder-frontend |
| Интеграция (17-19) | связка модулей | 1-2 | coder-backend + tester |
| Деплой (20-23) | конфиг + мониторинг | 1 | Lead + coder-backend |

Контекст забивается → закончить задачу → commit → новая сессия.

---

## 14. ЧЕКЛИСТ

- [x] Состав команды и роли
- [x] Реальный формат Claude Code (YAML frontmatter)
- [x] permissionMode: acceptEdits (не default)
- [x] maxTurns: 25 (защита от зацикливания)
- [x] Файловая структура
- [x] State management: 2 файла, tasks.json = source of truth
- [x] current — массив (параллельные задачи)
- [x] Контракты хранятся в tasks.json
- [x] Архивация done-шагов (tasks.json не раздувается)
- [x] Протокол сессий (с pytest на старте)
- [x] Resume для ретраев
- [x] Feedback loop (ошибки → ретроспектива → коррекция промптов)
- [x] Ревью agent-memory (каждые 5 задач)
- [x] Compaction стратегия
- [x] Rollback стратегия
- [x] Known limitations (frontend: TS проверяется через `tsc --noEmit`)
- [x] Аудит старых тестов перед переносом
- [x] Spec-файлы для модулей с 5+ зависимостями
- [x] Чистая БД (без миграции старых данных)
- [x] Единая LLM-обёртка (shared/llm_client.py)
- [x] Матрица взаимодействия APScheduler jobs
- [x] Критик-ревьюер (critic.md): 5 чеклистов, 2 точки входа
- [x] Самопроверка в промптах coder-backend, coder-frontend, tester
- [ ] **Мониторинг токенов** — отслеживать вручную
