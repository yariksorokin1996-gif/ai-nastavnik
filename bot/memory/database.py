import json
import aiosqlite
from datetime import datetime
from typing import Optional
from shared.config import DB_PATH

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    phase TEXT DEFAULT 'onboarding',
    goal TEXT,
    goal_deadline TEXT,
    area TEXT,
    seriousness INTEGER,
    sessions_count INTEGER DEFAULT 0,
    is_premium INTEGER DEFAULT 0,
    coaching_style INTEGER DEFAULT 2,
    mode TEXT DEFAULT 'coaching',
    patterns_detected TEXT DEFAULT '[]',
    commitments TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    pattern_type TEXT NOT NULL,
    pattern_text TEXT,
    count INTEGER DEFAULT 1,
    confronted INTEGER DEFAULT 0,
    detected_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    commitment TEXT,
    completed INTEGER,
    response TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()

        # Migration: add mode column for existing users
        try:
            await db.execute("ALTER TABLE users ADD COLUMN mode TEXT DEFAULT 'coaching'")
            await db.commit()
        except Exception:
            pass  # Column already exists


async def get_user(telegram_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                user = dict(row)
                user["patterns_detected"] = json.loads(user["patterns_detected"] or "[]")
                user["commitments"] = json.loads(user["commitments"] or "[]")
                return user
            return None


async def create_user(telegram_id: int, name: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, name) VALUES (?, ?)",
            (telegram_id, name),
        )
        await db.commit()
    return await get_user(telegram_id)


async def update_user(telegram_id: int, **fields):
    if not fields:
        return
    for key in ["patterns_detected", "commitments"]:
        if key in fields and isinstance(fields[key], list):
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [telegram_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {set_clause} WHERE telegram_id = ?", values
        )
        await db.commit()


async def add_message(telegram_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (telegram_id, role, content) VALUES (?, ?, ?)",
            (telegram_id, role, content),
        )
        await db.commit()


async def get_recent_messages(telegram_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT role, content FROM messages
               WHERE telegram_id = ?
               ORDER BY id DESC LIMIT ?""",
            (telegram_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]


async def add_pattern(telegram_id: int, pattern_type: str, pattern_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, count FROM patterns WHERE telegram_id = ? AND pattern_type = ?",
            (telegram_id, pattern_type),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing:
            await db.execute(
                "UPDATE patterns SET count = count + 1 WHERE id = ?", (existing[0],)
            )
        else:
            await db.execute(
                "INSERT INTO patterns (telegram_id, pattern_type, pattern_text) VALUES (?, ?, ?)",
                (telegram_id, pattern_type, pattern_text),
            )
        await db.commit()


async def get_patterns(telegram_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM patterns WHERE telegram_id = ? ORDER BY count DESC",
            (telegram_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT telegram_id, name, phase, goal FROM users") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_active_users(days: int = 7) -> list[dict]:
    """Return users who sent a message within the last N days."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT DISTINCT u.telegram_id, u.name, u.phase, u.goal
               FROM users u
               WHERE u.phase != 'onboarding'
               AND u.telegram_id IN (
                   SELECT DISTINCT telegram_id FROM messages
                   WHERE created_at > datetime('now', ? || ' days')
               )""",
            (f"-{days}",),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def increment_sessions(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET sessions_count = sessions_count + 1 WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()
