"""
Модуль базы данных Евы.
17 таблиц, init_db(), CRUD для каждой таблицы.
SQLite + aiosqlite + WAL mode.
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from shared.config import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _parse_json(text: str, default=None):
    """Безопасный парсинг JSON. Логирует ошибки, возвращает default."""
    if text is None:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("_parse_json failed: %s | text[:80]=%r", exc, str(text)[:80])
        return default if default is not None else {}


def _to_json(obj) -> str:
    """json.dumps с ensure_ascii=False."""
    return json.dumps(obj, ensure_ascii=False)


def _now() -> str:
    """UTC datetime строкой, совместимо с SQLite datetime('now')."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Соединение
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_db():
    """Открывает соединение с WAL + FK, возвращает через yield, закрывает в finally."""
    db = await aiosqlite.connect(DB_PATH)
    try:
        # WAL — вне транзакции (PRAGMA не требует транзакции)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# DDL — 17 таблиц
# ---------------------------------------------------------------------------

_CREATE_TABLES = """
-- Удаляем старую таблицу
DROP TABLE IF EXISTS checkins;

-- 1. users
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    name TEXT,
    current_phase TEXT NOT NULL DEFAULT 'ЗНАКОМСТВО',
    messages_total INTEGER NOT NULL DEFAULT 0,
    last_message_at TEXT,
    needs_full_update INTEGER NOT NULL DEFAULT 0,
    registration_day INTEGER NOT NULL DEFAULT 1,
    timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
    last_full_update_at TEXT,
    last_automated_msg_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    char_length INTEGER,
    source TEXT NOT NULL DEFAULT 'user',
    is_voice INTEGER NOT NULL DEFAULT 0,
    response_latency_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_telegram ON messages(telegram_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

-- 3. semantic_profiles
CREATE TABLE IF NOT EXISTS semantic_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE REFERENCES users(telegram_id),
    profile_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    tokens_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 4. profile_versions
CREATE TABLE IF NOT EXISTS profile_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    version INTEGER NOT NULL,
    profile_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pv_telegram ON profile_versions(telegram_id);

-- 5. episodes
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    emotional_tone TEXT,
    key_insight TEXT,
    commitments_json TEXT DEFAULT '[]',
    techniques_worked_json TEXT DEFAULT '[]',
    techniques_failed_json TEXT DEFAULT '[]',
    messages_count INTEGER NOT NULL DEFAULT 0,
    session_start TEXT NOT NULL,
    session_end TEXT NOT NULL,
    tokens_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_episodes_telegram ON episodes(telegram_id);
CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);

-- 6. procedural_memory
CREATE TABLE IF NOT EXISTS procedural_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE REFERENCES users(telegram_id),
    memory_json TEXT NOT NULL DEFAULT '{}',
    tokens_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 7. patterns
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    pattern_type TEXT NOT NULL,
    pattern_text TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    confronted INTEGER NOT NULL DEFAULT 0,
    detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_patterns_telegram ON patterns(telegram_id);

-- 8. phase_transitions
CREATE TABLE IF NOT EXISTS phase_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    from_phase TEXT NOT NULL,
    to_phase TEXT NOT NULL,
    reason TEXT,
    messages_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 9. goals
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    archived_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_goals_telegram ON goals(telegram_id);

-- 10. goal_steps
CREATE TABLE IF NOT EXISTS goal_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    title TEXT NOT NULL,
    deadline_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_steps_goal ON goal_steps(goal_id);
CREATE INDEX IF NOT EXISTS idx_steps_telegram ON goal_steps(telegram_id);
CREATE INDEX IF NOT EXISTS idx_steps_deadline ON goal_steps(deadline_at);

-- 11. daily_messages
CREATE TABLE IF NOT EXISTS daily_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    message_text TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    sent_at TEXT,
    opened INTEGER DEFAULT 0,
    responded INTEGER DEFAULT 0,
    response_delay_minutes INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 12. session_feedback
CREATE TABLE IF NOT EXISTS session_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    episode_id INTEGER REFERENCES episodes(id),
    session_end TEXT NOT NULL,
    messages_in_session INTEGER NOT NULL DEFAULT 0,
    feeling_after INTEGER,
    tried_in_practice INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sf_telegram ON session_feedback(telegram_id);

-- 13. analytics_weekly
CREATE TABLE IF NOT EXISTS analytics_weekly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 14. webapp_events
CREATE TABLE IF NOT EXISTS webapp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    event_type TEXT NOT NULL,
    page TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_we_telegram ON webapp_events(telegram_id);
CREATE INDEX IF NOT EXISTS idx_we_created ON webapp_events(created_at);

-- 15. processed_messages (idempotency)
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id INTEGER PRIMARY KEY,
    telegram_id INTEGER NOT NULL,
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 16. pending_facts (буфер мини-обновлений)
CREATE TABLE IF NOT EXISTS pending_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    fact_type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pf_telegram ON pending_facts(telegram_id);

-- 17. emotion_log (regex-эмоции)
CREATE TABLE IF NOT EXISTS emotion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    emotion TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_el_telegram ON emotion_log(telegram_id);
"""


async def init_db():
    """Создаёт все 17 таблиц. Безопасен для повторного вызова."""
    async with get_db() as db:
        await db.executescript(_CREATE_TABLES)
        await db.commit()
    logger.info("init_db: 17 таблиц готовы (%s)", DB_PATH)


# ---------------------------------------------------------------------------
# CRUD — Users
# ---------------------------------------------------------------------------

_USER_UPDATABLE_FIELDS = frozenset({
    "name",
    "current_phase",
    "messages_total",
    "last_message_at",
    "needs_full_update",
    "registration_day",
    "timezone",
    "last_full_update_at",
    "last_automated_msg_at",
    "updated_at",
})


async def get_user(telegram_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_user(telegram_id: int, name: str = None) -> dict:
    now = _now()
    async with get_db() as db:
        await db.execute(
            """INSERT OR IGNORE INTO users
               (telegram_id, name, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, name, now, now),
        )
        await db.commit()
    return await get_user(telegram_id)


async def update_user(telegram_id: int, **fields):
    if not fields:
        return
    bad = set(fields) - _USER_UPDATABLE_FIELDS
    if bad:
        raise ValueError(f"update_user: недопустимые поля: {bad}")
    fields.setdefault("updated_at", _now())
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [telegram_id]
    async with get_db() as db:
        await db.execute(
            f"UPDATE users SET {cols} WHERE telegram_id = ?", vals  # noqa: S608
        )
        await db.commit()


async def get_users_needing_update() -> list[int]:
    """WHERE needs_full_update=1 AND last_message_at < now()-30min."""
    async with get_db() as db:
        async with db.execute(
            """SELECT telegram_id FROM users
               WHERE needs_full_update = 1
                 AND last_message_at < datetime('now', '-30 minutes')"""
        ) as cur:
            return [row[0] for row in await cur.fetchall()]


async def get_silent_users(hours: int = 72) -> list[dict]:
    """Пользователи без сообщений >= hours часов (для silence_reminder)."""
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM users
               WHERE last_message_at < datetime('now', ? || ' hours')
                 AND last_message_at IS NOT NULL""",
            (f"-{hours}",),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_users() -> list[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM users") as cur:
            return [dict(r) for r in await cur.fetchall()]


# ---------------------------------------------------------------------------
# CRUD — Messages
# ---------------------------------------------------------------------------


async def add_message(
    telegram_id: int,
    role: str,
    content: str,
    source: str = "user",
    is_voice: int = 0,
    response_latency_ms: int = None,
) -> int:
    """Добавляет сообщение, возвращает id."""
    now = _now()
    char_length = len(content) if content else 0
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO messages
               (telegram_id, role, content, char_length, source, is_voice,
                response_latency_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (telegram_id, role, content, char_length, source, is_voice,
             response_latency_ms, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_recent_messages(telegram_id: int, limit: int = 20) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM messages
               WHERE telegram_id = ?
               ORDER BY id DESC LIMIT ?""",
            (telegram_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in reversed(rows)]


async def get_messages_since(telegram_id: int, since_dt: str) -> list[dict]:
    """Сообщения с момента since_dt (для full_memory_update)."""
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM messages
               WHERE telegram_id = ? AND created_at >= ?
               ORDER BY id ASC""",
            (telegram_id, since_dt),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_old_messages(days: int = 90):
    """Retention: удалить сообщения старше days дней."""
    async with get_db() as db:
        await db.execute(
            "DELETE FROM messages WHERE created_at < datetime('now', ? || ' days')",
            (f"-{days}",),
        )
        await db.commit()
    logger.info("delete_old_messages: удалены записи старше %d дней", days)


# ---------------------------------------------------------------------------
# CRUD — Processed messages (idempotency)
# ---------------------------------------------------------------------------


async def is_message_processed(message_id: int) -> bool:
    async with get_db() as db:
        async with db.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ?",
            (message_id,),
        ) as cur:
            return await cur.fetchone() is not None


async def mark_message_processed(message_id: int, telegram_id: int):
    async with get_db() as db:
        await db.execute(
            """INSERT OR IGNORE INTO processed_messages
               (message_id, telegram_id, received_at)
               VALUES (?, ?, ?)""",
            (message_id, telegram_id, _now()),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Semantic profiles
# ---------------------------------------------------------------------------


async def get_profile(telegram_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM semantic_profiles WHERE telegram_id = ?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            result = dict(row)
            result["profile_json"] = _parse_json(result["profile_json"])
            return result


async def upsert_profile(telegram_id: int, profile_json: dict, tokens_count: int):
    """INSERT OR REPLACE + автоматическая запись в profile_versions."""
    now = _now()
    json_str = _to_json(profile_json)
    async with get_db() as db:
        # Узнаём текущую версию
        async with db.execute(
            "SELECT version FROM semantic_profiles WHERE telegram_id = ?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
        new_version = (row[0] + 1) if row else 1

        await db.execute(
            """INSERT INTO semantic_profiles
               (telegram_id, profile_json, version, tokens_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   profile_json = excluded.profile_json,
                   version = excluded.version,
                   tokens_count = excluded.tokens_count,
                   updated_at = excluded.updated_at""",
            (telegram_id, json_str, new_version, tokens_count, now, now),
        )
        # Версия в архив
        await db.execute(
            """INSERT INTO profile_versions
               (telegram_id, version, profile_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, new_version, json_str, now),
        )
        await db.commit()
    logger.info("upsert_profile: user=%s version=%d", telegram_id, new_version)


async def get_profile_version(telegram_id: int, version: int) -> Optional[dict]:
    """Получить конкретную версию профиля из profile_versions."""
    async with get_db() as db:
        async with db.execute(
            "SELECT profile_json FROM profile_versions WHERE telegram_id = ? AND version = ?",
            (telegram_id, version),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return _parse_json(row[0])


# ---------------------------------------------------------------------------
# CRUD — Episodes
# ---------------------------------------------------------------------------


async def create_episode(
    telegram_id: int,
    title: str,
    summary: str,
    emotional_tone: str = None,
    key_insight: str = None,
    commitments_json: list = None,
    techniques_worked_json: list = None,
    techniques_failed_json: list = None,
    messages_count: int = 0,
    session_start: str = None,
    session_end: str = None,
    tokens_count: int = 0,
) -> int:
    now = _now()
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO episodes
               (telegram_id, title, summary, emotional_tone, key_insight,
                commitments_json, techniques_worked_json, techniques_failed_json,
                messages_count, session_start, session_end,
                tokens_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                telegram_id, title, summary, emotional_tone, key_insight,
                _to_json(commitments_json or []),
                _to_json(techniques_worked_json or []),
                _to_json(techniques_failed_json or []),
                messages_count,
                session_start or now, session_end or now,
                tokens_count, now,
            ),
        )
        await db.commit()
        return cur.lastrowid


async def get_episode_headers(telegram_id: int) -> list[dict]:
    """Только id, title, created_at — для выбора конспектов."""
    async with get_db() as db:
        async with db.execute(
            """SELECT id, title, created_at FROM episodes
               WHERE telegram_id = ?
               ORDER BY created_at DESC""",
            (telegram_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_episodes_by_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    async with get_db() as db:
        async with db.execute(
            f"SELECT * FROM episodes WHERE id IN ({placeholders})",  # noqa: S608
            ids,
        ) as cur:
            rows = await cur.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["commitments_json"] = _parse_json(d.get("commitments_json"), [])
                d["techniques_worked_json"] = _parse_json(d.get("techniques_worked_json"), [])
                d["techniques_failed_json"] = _parse_json(d.get("techniques_failed_json"), [])
                results.append(d)
            return results


# ---------------------------------------------------------------------------
# CRUD — Procedural memory
# ---------------------------------------------------------------------------


async def get_procedural(telegram_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM procedural_memory WHERE telegram_id = ?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            result = dict(row)
            result["memory_json"] = _parse_json(result["memory_json"])
            return result


async def upsert_procedural(telegram_id: int, memory_json: dict, tokens_count: int):
    now = _now()
    json_str = _to_json(memory_json)
    async with get_db() as db:
        await db.execute(
            """INSERT INTO procedural_memory
               (telegram_id, memory_json, tokens_count, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   memory_json = excluded.memory_json,
                   tokens_count = excluded.tokens_count,
                   updated_at = excluded.updated_at""",
            (telegram_id, json_str, tokens_count, now),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Pending facts
# ---------------------------------------------------------------------------


async def add_pending_fact(
    telegram_id: int,
    fact_type: str,
    content: str,
    confidence: str = "medium",
):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO pending_facts
               (telegram_id, fact_type, content, confidence, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, fact_type, content, confidence, _now()),
        )
        await db.commit()


async def get_pending_facts(telegram_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM pending_facts
               WHERE telegram_id = ?
               ORDER BY created_at ASC""",
            (telegram_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def clear_pending_facts(telegram_id: int):
    async with get_db() as db:
        await db.execute(
            "DELETE FROM pending_facts WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Emotion log
# ---------------------------------------------------------------------------


async def add_emotion(telegram_id: int, emotion: str):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO emotion_log (telegram_id, emotion, created_at)
               VALUES (?, ?, ?)""",
            (telegram_id, emotion, _now()),
        )
        await db.commit()


async def get_recent_emotions(telegram_id: int, limit: int = 10) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM emotion_log
               WHERE telegram_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (telegram_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# CRUD — Patterns
# ---------------------------------------------------------------------------


async def add_or_increment_pattern(
    telegram_id: int,
    pattern_type: str,
    pattern_text: str,
):
    """INSERT или UPDATE count+1."""
    async with get_db() as db:
        async with db.execute(
            """SELECT id FROM patterns
               WHERE telegram_id = ? AND pattern_type = ? AND pattern_text = ?""",
            (telegram_id, pattern_type, pattern_text),
        ) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute(
                "UPDATE patterns SET count = count + 1 WHERE id = ?",
                (row[0],),
            )
        else:
            await db.execute(
                """INSERT INTO patterns
                   (telegram_id, pattern_type, pattern_text, detected_at)
                   VALUES (?, ?, ?, ?)""",
                (telegram_id, pattern_type, pattern_text, _now()),
            )
        await db.commit()


async def get_patterns(telegram_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM patterns
               WHERE telegram_id = ?
               ORDER BY count DESC""",
            (telegram_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ---------------------------------------------------------------------------
# CRUD — Phase transitions
# ---------------------------------------------------------------------------


async def add_phase_transition(
    telegram_id: int,
    from_phase: str,
    to_phase: str,
    reason: str,
    messages_count: int,
):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO phase_transitions
               (telegram_id, from_phase, to_phase, reason, messages_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, from_phase, to_phase, reason, messages_count, _now()),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Goals
# ---------------------------------------------------------------------------


async def create_goal(telegram_id: int, title: str) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO goals (telegram_id, title, created_at)
               VALUES (?, ?, ?)""",
            (telegram_id, title, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def get_active_goal(telegram_id: int) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM goals
               WHERE telegram_id = ? AND status = 'active'
               LIMIT 1""",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_goal_status(
    goal_id: int,
    status: str,
    completed_at: str = None,
    archived_at: str = None,
):
    async with get_db() as db:
        await db.execute(
            """UPDATE goals
               SET status = ?, completed_at = ?, archived_at = ?
               WHERE id = ?""",
            (status, completed_at, archived_at, goal_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Goal steps
# ---------------------------------------------------------------------------


async def add_goal_step(
    goal_id: int,
    telegram_id: int,
    title: str,
    sort_order: int = 0,
    deadline_at: str = None,
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO goal_steps
               (goal_id, telegram_id, title, sort_order, deadline_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (goal_id, telegram_id, title, sort_order, deadline_at, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def update_step_status(
    step_id: int,
    status: str,
    completed_at: str = None,
):
    async with get_db() as db:
        await db.execute(
            """UPDATE goal_steps
               SET status = ?, completed_at = ?
               WHERE id = ?""",
            (status, completed_at, step_id),
        )
        await db.commit()


async def get_goal_steps(goal_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM goal_steps
               WHERE goal_id = ?
               ORDER BY sort_order ASC""",
            (goal_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_steps_by_deadline(telegram_id: int, date_str: str) -> list[dict]:
    """Шаги с deadline_at на указанную дату. date_str формат: 'YYYY-MM-DD'."""
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM goal_steps
               WHERE telegram_id = ? AND date(deadline_at) = ? AND status = 'pending'
               ORDER BY sort_order ASC""",
            (telegram_id, date_str),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_overdue_steps(telegram_id: int) -> list[dict]:
    """Просроченные шаги: pending AND deadline < now - 1 hour."""
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM goal_steps
               WHERE telegram_id = ? AND status = 'pending'
                 AND deadline_at < datetime('now', '-1 hour')
               ORDER BY deadline_at ASC""",
            (telegram_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ---------------------------------------------------------------------------
# CRUD — Daily messages
# ---------------------------------------------------------------------------


async def create_daily_message(
    telegram_id: int,
    message_text: str,
    day_number: int,
) -> int:
    now = _now()
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO daily_messages
               (telegram_id, message_text, day_number, sent_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, message_text, day_number, now, now),
        )
        await db.commit()
        return cur.lastrowid


async def mark_daily_responded(daily_id: int, response_delay_minutes: int):
    async with get_db() as db:
        await db.execute(
            """UPDATE daily_messages
               SET responded = 1, response_delay_minutes = ?
               WHERE id = ?""",
            (response_delay_minutes, daily_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Session feedback
# ---------------------------------------------------------------------------


async def create_feedback(
    telegram_id: int,
    episode_id: int,
    session_end: str,
    messages_in_session: int,
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO session_feedback
               (telegram_id, episode_id, session_end, messages_in_session, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, episode_id, session_end, messages_in_session, _now()),
        )
        await db.commit()
        return cur.lastrowid


async def update_feeling(feedback_id: int, feeling_after: int):
    async with get_db() as db:
        await db.execute(
            "UPDATE session_feedback SET feeling_after = ? WHERE id = ?",
            (feeling_after, feedback_id),
        )
        await db.commit()


async def update_enactment(feedback_id: int, tried_in_practice: int):
    async with get_db() as db:
        await db.execute(
            "UPDATE session_feedback SET tried_in_practice = ? WHERE id = ?",
            (tried_in_practice, feedback_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Analytics weekly
# ---------------------------------------------------------------------------


async def save_weekly_report(week_start: str, week_end: str, report_json: dict):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO analytics_weekly
               (week_start, week_end, report_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (week_start, week_end, _to_json(report_json), _now()),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Webapp events
# ---------------------------------------------------------------------------


async def add_webapp_event(
    telegram_id: int,
    event_type: str,
    page: str = None,
    metadata: dict = None,
):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO webapp_events
               (telegram_id, event_type, page, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                telegram_id,
                event_type,
                page,
                _to_json(metadata) if metadata else None,
                _now(),
            ),
        )
        await db.commit()


async def delete_old_webapp_events(days: int = 90):
    """Retention: удалить webapp_events старше days дней."""
    async with get_db() as db:
        await db.execute(
            "DELETE FROM webapp_events WHERE created_at < datetime('now', ? || ' days')",
            (f"-{days}",),
        )
        await db.commit()
    logger.info("delete_old_webapp_events: удалены записи старше %d дней", days)


# ---------------------------------------------------------------------------
# Retention (общая)
# ---------------------------------------------------------------------------


async def retention_cleanup(msg_days: int = 90, events_days: int = 90):
    """Вызывает delete_old_messages + delete_old_webapp_events."""
    await delete_old_messages(days=msg_days)
    await delete_old_webapp_events(days=events_days)
