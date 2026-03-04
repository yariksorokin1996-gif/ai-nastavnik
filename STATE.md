# AI Наставник — STATE.md

## Фаза: АРХИТЕКТУРА (Фаза 2)
## Подэтап: Шаги 0-11 завершены. Следующий: шаг 12 (session_manager + full_memory_update + handlers)

## ТЗ
MVP тестируем на **10 друзьях**. Без подписки. Webapp включён. Тёмная тема включена.
Гипотеза: «5/10 тестеров вернутся (3+ msg) через D3 без push от бота.»
Бюджет до MVP: ~$115-120.

## Что сделано

### Продуктовая проработка
- ✅ Полный аудит текущего кода (бэкенд + фронтенд + промпты)
- ✅ Раздел ПАМЯТЬ проработан → `docs/01_memory.md`
- ✅ Продуктовые решения утверждены (путь, поток vs сессии, первый контакт)
- ✅ **Бот = Ева**, женский, тёплая подруга-наставница
- ✅ **3 режима спроектированы** (MVP = только «Тёплая подруга»)
- ✅ **Исследование промптов** для всех 3 режимов
- ✅ **Написан полный промпт Евы** → `docs/02_prompts.md`
- ✅ **Все 7 несоответствий закрыты**

### Технические решения
- ✅ Токен-бюджет: мягкий лимит **3800** (запас 10% от 4200)
- ✅ Модели: Sonnet (диалог) + GPT-4o-mini (фоновое) ≈ $7/мес на юзера
- ✅ Обновление памяти: мини (regex) + полное (пауза 30 мин)
- ✅ Фазовые переходы: пороги + LLM-оценка каждые 10 сообщений
- ✅ Экономика пересчитана (включая фанатов)

### Аудит и план v5 (сессия 03.03.2026)
- ✅ **Аудит плана** от 6 экспертов (CFO, CPO, Designer, Tech Lead, DevOps, CISO) → `docs/correct.md`
- ✅ **80+ вопросов отвечены**, 13 стоп-факторов закрыты
- ✅ **Plan.md переписан v5** — две части: для владельца + ТЗ для агентов
- ✅ **Ключевые изменения из аудита:**
  - 10 тестеров (не 3-5)
  - Webapp в MVP обязательно
  - Тёмная тема в MVP (нативная, не хак)
  - Аффирмация дня: гибрид (банк цитат → GPT с контекстом)
  - Карта людей = часть профиля (не отдельная таблица)
  - /export убран из MVP, /forget и /delete_account добавлены
  - profile_versions таблица добавлена
  - WAL mode, idempotency, rate limiting, owner check
  - Healthcheck + бэкапы + 90-дневный retention сообщений
  - Prompt injection защита
  - Disclaimer при /start
  - Контраст: #D4466A для текста (WCAG AA)

### Архитектура агентов v2.2 (сессия 03.03.2026)
- ✅ **3 раунда критики** — найдено 14 проблем, все исправлены
- ✅ **Проверка фич Claude Code** — кастомные агенты, tool restrictions, persistent memory — работает
- ✅ **agplan.md v2.2** — финальная версия:
  - Формат: реальный YAML frontmatter Claude Code
  - 3 агента: coder-backend, coder-frontend, tester (permissionMode: acceptEdits, maxTurns: 25)
  - State: 2 файла (STATE.md + tasks.json), tasks.json = source of truth
  - current — массив (поддержка параллельных задач)
  - Контракты хранятся в tasks.json (поле contract)
  - Resume для ретраев (не новый вызов)
  - Архивация done-шагов (tasks.json не раздувается)
  - **Feedback loop**: ошибки → ретроспектива (>=3 ошибок) → коррекция промптов (секция «Уроки», лимит 10)
  - Ревью agent-memory каждые 5 задач
  - Эскалация: промпт → memory → чеклист ревью (2 шанса)
  - Стратегия compaction + rollback

### Критический анализ + закрытие 12 дыр (сессия 03.03.2026)
- ✅ **Критика plan.md + agplan.md** — найдено 12 проблем (3 блокера, 5 замедлителей, 4 мелочи)
- ✅ **Все 12 закрыты:**
  - Spec-файлы для модулей с 5+ зависимостями (session_manager, context_builder, full_memory_update)
  - Примеры вызовов к каждому контракту (не только сигнатуры)
  - Node.js установлен локально → coder-frontend проверяет TypeScript (`tsc --noEmit`)
  - Шаг 7 расширен: DoD + требования к 8 промптам → `docs/07_prompts_spec.md`
  - Мьютекс: `dict[int, asyncio.Lock]` с ленивым созданием
  - Матрица взаимодействия 7 APScheduler jobs + защита от двойных сообщений
  - Единая LLM-обёртка `shared/llm_client.py` (Claude timeout=30 retry=1, GPT timeout=15 retry=2)
  - **Чистая БД для MVP** (без миграции старых данных, без ALTER TABLE)
  - Deep link формат: `Telegram.WebApp.openTelegramLink()`
- ✅ **plan.md обновлён до v5.3**
- ✅ **agplan.md обновлён до v2.2**

### Аналитика MVP (сессия 03.03.2026)
- ✅ **Исследование 10 компаний** (Replika, Pi, Woebot, BetterUp, Wysa, Character.AI, Youper, Noom, Headspace/Ebb, Calm)
- ✅ **North Star метрика:** «стало ли лучше после разговора» (>=70%)
- ✅ **10 метрик успеха** с порогами и источниками → plan.md
- ✅ **Decision tree:** 7 сценариев «если метрика ниже порога → что делать»
- ✅ **Ежедневный отчёт:** 15 метрик в Telegram (09:00 MSK)
- ✅ **Еженедельная сводка:** LLM-анализ качества + тренды + рекомендации (вс 12:00)
- ✅ **Feedback collector:** inline-кнопки Telegram (не regex), feeling + enactment
- ✅ **Webapp-трекинг:** 8 типов событий + throttle + retention 90 дней
- ✅ **Realtime-алерты:** Alerter (пустая память, latency, кризис уровня 3)
- ✅ **Шаблон интервью:** 6 вопросов, 15 мин, подготовка + follow-up
- ✅ **10 технических дыр закрыты** (timing, episode_id, regex, enactment, LLM volume, retention, jobs, alerts, cost, privacy)
- ✅ **Стоимость аналитики:** ~$0.20/мес (пренебрежимо)
- ✅ **Plan.md обновлён v5.1** — аналитика добавлена в обе части
- ✅ **Шаг 23 расширен** на 23.1-23.5 (отчёт, сводка, webapp, feedback, интервью)
- ✅ **Ревью plan.md** — найдено 6 проблем + 3 мелочи, все исправлены:
  - Секция 6.3/6.4 → ссылка на шаг 23 (убрано дублирование)
  - Добавлен блок 3Ж (аналитика) + 4.6 (webapp analytics)
  - Шаг 23 = проверка, не сборка (код → Фаза 3-4)
  - One-shot jobs → логика в full_memory_update (не теряются при рестарте)
  - Callback-хэндлеры для inline-кнопок описаны в 3.15
  - 3 новых E2E теста аналитики (E2E-6, 7, 8)
  - «7 промптов» → «8 промптов», retention уточнён, NPS → качественная метрика
- ✅ **Plan.md обновлён до v5.2**

### Инфраструктура агентов (сессия 03.03.2026)
- ✅ **Шаг 0 выполнен** — инфраструктура агентов готова:
  - `.claude/agents/` — 3 агента (coder-backend, coder-frontend, tester)
  - `.claude/agent-memory/` — персистентная память (пустая)
  - `.claude/CLAUDE.md` — правила проекта
  - `.state/tasks.json` — 23 шага, tasks.json = source of truth
  - `tests/` — структура (conftest.py + unit/integration/e2e)
  - Аудит тестов: test_critical.py (80 сценариев), test_scenarios.py (8), test_dialog.py (1) — все мёртвые (не pytest, зависят от старого API). Удалены.

### Документация шагов 2-4 (сессия 03.03.2026)
- ✅ **Шаг 2:** Движок диалога → `docs/04_dialog_engine.md`
  - 14 шагов обработки сообщения + диаграмма потока
  - Таблица обрезки контекста (8 приоритетов)
  - Мини-обновление (regex, без LLM)
  - Полное обновление (APScheduler, GPT-4o-mini)
  - Кризис: 3 уровня + false positive защита
  - Матрица взаимодействия APScheduler jobs
- ✅ **Шаг 3:** 20 тестовых сценариев → `docs/05_test_scenarios.md`
  - 4 знакомство + 3 зеркало + 3 кризис + 3 возвращение + 3 цели + 2 память + 2 edge-case
  - Рубрика оценки: 5 критериев × 5 баллов
  - Порог: avg >= 4.0, кризисные >= 4.0 (блокер)
- ✅ **Шаг 4:** Макеты экранов → `docs/06_webapp_mockups.md`
  - 5 экранов: Сегодня (новый), Сегодня (активный), Мой путь, Профиль, Навигация
  - Светлая + тёмная тема (CSS-переменные)
  - Убрано из MVP: подписка, режимы, стиль, таро
  - Добавлено: /forget, /delete_account, дисклеймер
- ✅ **CLAUDE.md обновлён** — добавлены 7 блоков рабочего протокола лида

### Шаг 5: Схема БД (сессия 03.03.2026)
- ✅ **database.py полностью перезаписан** — 17 таблиц + 40 CRUD-функций
  - Субагент coder-backend написал код, лид провёл ревью
  - Субагент tester написал 41 тест, все зелёные (0.70s)
  - WAL mode, FK, idempotency, whitelist validation, retention
  - 3 таблицы из dialog engine добавлены (processed_messages, pending_facts, emotion_log)
  - 2 недостающих поля users (last_full_update_at, last_automated_msg_at)
- ✅ **CLAUDE.md: СТОП-сигнал** — «лид НЕ пишет код при наличии субагентов»
- ✅ **agent-memory/lessons.md** — первый урок зафиксирован

### Шаг 6: Контракты модулей (сессия 03.03.2026)
- ✅ **3 spec-файла** для модулей с 5+ зависимостями:
  - `specs/context_builder_spec.md` — 8 переменных, обрезка по 8 приоритетам, бюджет 3800 tok
  - `specs/full_memory_update_spec.md` — APScheduler job, 5 шагов, GPT-4o-mini, merge профиля
  - `specs/session_manager_spec.md` — 14 шагов, 10 зависимостей, мьютекс, кризис, rate limiting
- ✅ **16 контрактов модулей** в tasks.json (шаги 8-17):
  - Каждый контракт: сигнатура + типы + ошибки + пример вызова
  - Шаг 8 (4 задачи): llm_client, models, config, тесты
  - Шаг 9 (4 задачи): profile_manager, episode_manager, procedural_memory, тесты
  - Шаг 10 (4 задачи): context_builder, system_prompt, memory_prompts, тесты
  - Шаг 11 (3 задачи): phase_evaluator, goal_manager, тесты
  - Шаг 12 (5 задач): session_manager, full_memory_update, handlers, safety, тесты
  - Шаг 13 (2 задачи): daily_messenger, тесты
  - Шаг 14 (4 задачи): alerter, feedback_collector, reports, тесты
  - Шаги 15-17 (4 задачи): API endpoints, webapp экраны, тёмная тема, аналитика
- ✅ **Баг зафиксирован:** pattern_detector.py вызывает add_pattern() вместо add_or_increment_pattern()
- ✅ **Состояние кодовой базы задокументировано:** что переписать vs создать vs обновить

### Шаг 8: Фундамент — LLM-обёртка + модели + конфиг (сессия 03.03.2026)
- ✅ **shared/config.py обновлён** — убраны старые переменные (CLAUDE_MODEL_FAST, FREE_SESSIONS_LIMIT, MORNING/EVENING), добавлены 11 новых (CLAUDE_MODEL, GPT_MODEL, OWNER_TELEGRAM_ID, TOKEN_BUDGET_SOFT, RATE_LIMIT_PER_MINUTE, CLAUDE_TIMEOUT, GPT_TIMEOUT, FALLBACK_RESPONSE, FULL_UPDATE_PAUSE_MINUTES, ALERT_THRESHOLDS)
- ✅ **shared/llm_client.py создан** — call_claude (prompt caching, retry 1, fallback), call_gpt (retry 2, backoff, LLMError), LLMError exception, синглтон-клиенты, логирование tokens/latency
- ✅ **shared/models.py создан** — 16 Pydantic-моделей (SemanticProfile, Episode, CrisisResult, PhaseEvaluation, MiniUpdateResult и др.), все с ConfigDict(from_attributes=True)
- ✅ **36 тестов** — 13 llm_client (success, timeout, retry, auth, caching, json_format) + 20 models (все 16 моделей + ValidationError) + 3 config. Все зелёные (0.57с)
- ✅ **77 тестов всего** — 41 database + 36 новых, все зелёные (1.10с)

### Доработка шага 6 + Шаг 7: Промпты (сессия 03.03.2026)
- ✅ **Аудит шага 6** — 3 spec-файла ОК, CRUD-ссылки ОК, дополнены 8 контрактов (обработка ошибок) + примеры к 8.2/8.3
- ✅ **Шаг 7:** 10 промптов → `docs/07_prompts_spec.md`:
  - BASE_PROMPT — ссылка на docs/02_prompts.md
  - MINI_UPDATE_PATTERNS — regex для имён/обязательств/эмоций/возраста + тестовые строки
  - EPISODE_SUMMARY_PROMPT — конспект разговора (JSON)
  - PROFILE_UPDATE_PROMPT — diff-обновление профиля (JSON) + стоп-лист
  - EPISODE_SELECTION_PROMPT — выбор 2-3 релевантных конспектов (JSON)
  - PHASE_EVALUATION_PROMPT — оценка готовности к переходу фазы (JSON) + критерии для всех 6 фаз
  - CRISIS_VERIFICATION_PROMPT — LLM-верификация false positives (JSON, timeout 10с)
  - DAILY_MESSAGE_PROMPT — ежедневное сообщение (текст) + стоп-лист sensitive_topics
  - GOAL_STEPS_PROMPT — разбивка цели на 3-7 шагов (JSON)
  - WEEKLY_ANALYSIS_PROMPT — еженедельный анализ качества (JSON)
  - Каждый промпт: точный текст + JSON-схема + пример input/output + fallback
  - Сводная таблица fallback-ов

## Структура документации
```
docs/
├── 01_memory.md           ✅ Готов
├── 02_prompts.md          ✅ Готов
├── 03_phases.md           ✅ Готов (шаг 1)
├── 04_dialog_engine.md    ✅ Готов (шаг 2)
├── 05_test_scenarios.md   ✅ Готов (шаг 3)
├── 06_webapp_mockups.md   ✅ Готов (шаг 4)
├── 07_prompts_spec.md     ✅ Готов (шаг 7)
├── correct.md             ✅ Аудит + ответы
└── plan.md                ✅ v5.3

specs/
├── context_builder_spec.md    ✅ Готов (шаг 6)
├── full_memory_update_spec.md ✅ Готов (шаг 6)
└── session_manager_spec.md    ✅ Готов (шаг 6)
```

## 20 принятых решений (кратко)

| # | Решение |
|---|---------|
| 1 | 10 тестеров, webapp обязательно |
| 2 | Фазы только вперёд, 6 штук |
| 3 | Голосовые → текст (лимит 3 мин) |
| 4 | Ева пишет первой 7 дней, потом только при молчании |
| 5 | Цели на фазе ЦЕЛЬ (~50 сообщений) |
| 6 | Аффирмация: банк цитат → GPT с контекстом |
| 7 | Тёмная тема в MVP |
| 8 | /export убран, /forget + /delete_account добавлены |
| 9 | Карта людей в профиле |
| 10 | Мягкий лимит 3800 токенов |
| 11 | Rate limiting 60 req/min |
| 12 | Бэкапы ежедневно, retention 90 дней |
| 13 | North Star = «стало ли лучше» (>=70%) |
| 14 | Feedback через inline-кнопки, не regex |
| 15 | LLM-анализ по одному юзеру за запрос |
| 16 | Realtime-алерты при аномалиях (Alerter) |
| 17 | Анонимизация перед LLM-анализом |
| 18 | Аналитика: $0.20/мес (GPT-4o-mini) |
| 19 | Feedback НЕ one-shot jobs (устойчиво к рестарту) |
| 20 | Аналитика собирается в Фазе 3-4, шаг 23 = проверка |

### Шаг 9: Ядро памяти (сессия 03.03.2026)
- ✅ **database.py патч** — get_profile_version + techniques_worked/failed в episodes
- ✅ **profile_manager.py** — 5 функций (create, get, update с diff, rollback, as_text ≤1000 tok)
- ✅ **episode_manager.py** — 3 функции (create с GPT, find_relevant с LLM + keyword fallback, titles)
- ✅ **procedural_memory.py** — 3 функции (get, update merge, as_text ≤300 tok)
- ✅ **memory_prompts.py** — EPISODE_SUMMARY_PROMPT + EPISODE_SELECTION_PROMPT
- ✅ **74 теста шага 9** (31 profile + 22 episode + 21 procedural), все зелёные
- ✅ **114 тестов всего** — 41 database + 36 shared + 37 memory, все зелёные (4.3с)
- ✅ **CRITIC-2 шага 9:** 2×P1 (broad except) → FIXED. Остальное чисто.
- ✅ **Баг исправлен:** EPISODE_SELECTION_PROMPT — фигурные скобки экранированы для .format()

### Шаг 10: Контекст и промпт (сессия 04.03.2026)
- ✅ **system_prompt.py переписан** — убран «Алекс» (grep=0), промпт Евы + 6 фаз (~120 строк)
- ✅ **memory_prompts.py дополнен** — PROFILE_UPDATE_PROMPT + PHASE_EVALUATION_PROMPT + PHASE_TRANSITION_CRITERIA
- ✅ **context_builder.py переписан** — 7 секций, бюджет 3800, обрезка по 6 приоритетам, asyncio.gather, _safe_call (~277 строк)
- ✅ **21 тест** (13 system_prompt + 8 context_builder), все зелёные
- ✅ **135 тестов всего** — 41 database + 36 shared + 37 memory + 21 context/prompt, все зелёные (4.3с)
- ✅ **CRITIC-2:** PASS (0 P0, 0 P1, 5 P2 — все SKIP для MVP)

### Жёсткий аудит шага 10 + протокол UX (сессия 04.03.2026)
- ✅ **Аудит нашёл**: P0 (нет fallback procedural), P1 (тупая обрезка profile), P1 (мелкие тесты)
- ✅ **Протокол «Глазами пользователя»** — 2-уровневый:
  - Универсальное правило в CLAUDE.md + промптах 4 агентов (coder-backend, coder-frontend, tester, critic)
  - Проектные персоны в `docs/user_scenarios.md` (Маша/Аня/Лена)
  - Лид копирует сценарии в контракт каждой user-facing задачи
  - Чеклист А (план): пункт 8 — «есть секция Сценарии?»
  - Чеклист Д (critic): проверка fallback/полноты/паузы
  - agplan.md: шаг g-bis + секция 5.4
- ✅ **P0 исправлен**: `_FALLBACK_PROCEDURAL` для новых юзеров
- ✅ **P1 исправлен**: структурная обрезка profile (strengths/achievements первыми)
- ✅ **+4 теста**: procedural fallback, обрезка profile, пауза, commitments
- ✅ **139 тестов всего**, все зелёные

### Шаг 11: Фазы и цели (сессия 04.03.2026)
- ✅ **database.py патч** — add_goal_step + deadline_at, get_steps_by_deadline, get_overdue_steps
- ✅ **memory_prompts.py дополнен** — GOAL_STEPS_PROMPT (экранирован для .format())
- ✅ **phase_evaluator.py создан** — evaluate_phase (GPT-4o-mini), fallback='stay', РИТМ без LLM (~136 строк)
- ✅ **goal_manager.py создан** — 7 функций: create/generate_steps/complete/skip/today/overdue/archive (~214 строк)
- ✅ **19 тестов** (6 phase_evaluator + 13 goal_manager), все зелёные
- ✅ **158 тестов всего** — 41 database + 36 shared + 37 memory + 21 context/prompt + 6 phase + 13 goal + 4 доп., все зелёные (4.6с)
- ✅ **CRITIC-2:** PASS (0 P0, 1 P1 → FIXED, 2 P2 → SKIP)

## Следующие шаги

1. ~~**Шаг 0:** Инфраструктура агентов~~ ✅
2. ~~**Шаг 1:** 6 фаз общения~~ ✅
3. ~~**Шаг 2:** Движок диалога~~ ✅
4. ~~**Шаг 3:** Тестовые сценарии~~ ✅
5. ~~**Шаг 4:** Макеты экранов~~ ✅
6. ~~**Шаг 5:** Схема хранения данных (БД)~~ ✅
7. ~~**Шаг 6:** Контракты модулей (specs/)~~ ✅
8. ~~**Шаг 7:** Спецификация промптов (10 штук)~~ ✅
9. ~~**Шаг 8:** Фундамент — LLM-обёртка + Pydantic-модели + Config~~ ✅
10. ~~**Шаг 9:** Ядро памяти — profile + episodes + procedural~~ ✅ (CRITIC-2 пройден)
11. ~~**Шаг 10:** Контекст и промпт — context_builder + system_prompt + memory_prompts~~ ✅ (CRITIC-2 + аудит)
12. ~~**Шаг 11:** Фазы и цели — phase_evaluator + goal_manager~~ ✅ (CRITIC-2 пройден)
13. **Шаг 12:** Главный мотор — session_manager + full_memory_update + handlers ← СЛЕДУЮЩИЙ
14. После шага 12 → шаг 13 (daily_messenger)

## Нерешённые вопросы
Нет. Все стоп-факторы из аудита закрыты.

## Файлы плана
- Основной: `docs/plan.md` (v5.3 — 12 дыр закрыты)
- Агенты: `docs/agplan.md` (v2.2 — spec-файлы, TS-проверка, LLM-обёртка)
- Аудит: `docs/correct.md`
- Исследование аналитики: `.claude/plans/magical-coalescing-ladybug.md`
