# Ева — Telegram-бот

## Команды
- Тесты: pytest tests/ -v --cov=bot --cov-report=term-missing
- Линтер: ruff check bot/ shared/ backend/
- Быстрая проверка: pytest tests/ -x --tb=line -q
- Проверка TypeScript: cd webapp && npx tsc --noEmit

## Архитектура
- Бот: python-telegram-bot 21.6 (переход на aiogram запланирован)
- БД: SQLite + aiosqlite + WAL mode
- API: FastAPI (backend/api.py)
- Webapp: React 19 + Vite + TS (webapp/)
- LLM диалог: Claude Sonnet 4.5
- LLM фоновое: GPT-4o-mini

## Ключевые правила
- Фазы ТОЛЬКО вперёд (6 штук: ЗНАКОМСТВО → ЗЕРКАЛО → НАСТРОЙКА → ПОРТРЕТ → ЦЕЛЬ → РИТМ)
- Токен-бюджет: 3800 мягкий лимит
- Карта людей в profile_json.people, НЕ отдельная таблица
- Мини-обновление памяти: regex (НЕ LLM)
- Полное обновление: при паузе >= 30 мин
- Кризис: 3 уровня (суицид → шаблон, насилие → мягкое + Claude, грусть → эмпатия)
- Idempotency по message_id
- Rate limiting 60 req/min
- Мьютекс: dict[int, asyncio.Lock] с ленивым созданием

## Субагенты
- coder-backend: Python (Sonnet, acceptEdits, maxTurns 25)
- coder-frontend: React/TS (Sonnet, acceptEdits, maxTurns 25)
- tester: pytest (Sonnet, acceptEdits, maxTurns 25)
- critic: ревьюер (Sonnet, bypassPermissions, maxTurns 15, read-only)
- Исследование: встроенный Explore

## Критик (critic)
- CRITIC-1 (план): запускать ПЕРЕД делегацией кода — проверяет контракт + docs
- CRITIC-2 (результат): запускать ПОСЛЕ кода + тестов — проверяет код + тесты
- Не запускать: правка < 10 строк, hotfix
- Вердикт: PASS / FIX NEEDED / REWRITE + приоритеты P0/P1/P2
- P0 → FIX обязателен, P1 → FIX если быстро, P2 → можно пропустить

## Источники правды
- tasks.json = задачи и контракты (побеждает при конфликте с STATE.md)
- STATE.md = человекочитаемая сводка
- docs/plan.md = ТЗ проекта (v5.3)
- docs/agplan.md = протокол работы команды агентов

## Старт сессии
1. Прочитать STATE.md + .state/tasks.json
2. git status && git log --oneline -3
3. pytest tests/ -x --tb=line -q (если есть тесты)
4. Взять задачу из tasks.json → current

## СТОП-сигнал: код
Перед ЛЮБЫМ Write/Edit .py/.ts/.tsx/.css файла:
→ Есть субагенты? → ДА → ДЕЛЕГИРУЙ, не пиши сам.
→ Лид пишет только: docs, specs, STATE.md, tasks.json, CLAUDE.md.
Нарушение = ошибка протокола → запись в agent-memory/lessons.md.

## Рабочий цикл
- Документация (docs/, specs/): Lead пишет напрямую
- Код (.py/.ts/.tsx/.css): контракт → CRITIC-1 → субагент → tester → CRITIC-2 → pytest → commit
- Подробный протокол: docs/agplan.md секция 4.2

## Завершение сессии
1. pytest → всё зелёное?
2. Обновить STATE.md и tasks.json
3. git commit

## Правило 3 попыток
Агент ошибся → resume (не новый вызов). 3 попытки без результата → Lead чинит сам или спрашивает пользователя.

## Resume vs новый вызов
- Тесты красные / мелкие замечания → resume (контекст сохранён)
- Контракт изменился / новая задача → новый вызов

## Spec-файлы
Модуль с 5+ зависимостями → сначала specs/<module>_spec.md (алгоритм + примеры вызовов), потом агент.

## Триггеры (не забывать)
- Ошибка агента → записать в tasks.json log
- errors_since_retro >= 3 → ретроспектива (docs/agplan.md 8.2)
- Каждые 5 задач → ревью agent-memory (docs/agplan.md 8.5)
