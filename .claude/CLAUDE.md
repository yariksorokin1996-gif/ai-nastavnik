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
- Исследование: встроенный Explore

## Источники правды
- tasks.json = задачи и контракты (побеждает при конфликте с STATE.md)
- STATE.md = человекочитаемая сводка
- docs/plan.md = ТЗ проекта (v5.3)
- docs/agplan.md = протокол работы команды агентов
