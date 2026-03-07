"""Извлекает вчерашние сессии из БД Евы для анализа качества."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta


def extract(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 1. Все сообщения за вчера
    messages = conn.execute("""
        SELECT m.telegram_id, m.role, m.content, m.created_at, m.source,
               m.response_latency_ms, m.is_voice
        FROM messages m
        WHERE DATE(m.created_at) = ?
        ORDER BY m.telegram_id, m.created_at
    """, (yesterday,)).fetchall()

    # 2. Контекст юзеров (фаза, messages_total, профиль, running_summary)
    user_ids = set(m["telegram_id"] for m in messages)
    users = {}
    for tid in user_ids:
        u = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (tid,)
        ).fetchone()
        sp = conn.execute(
            "SELECT profile_json FROM semantic_profiles WHERE telegram_id = ?",
            (tid,),
        ).fetchone()
        pm = conn.execute(
            "SELECT memory_json FROM procedural_memory WHERE telegram_id = ?",
            (tid,),
        ).fetchone()
        users[tid] = {
            "name": u["name"] if u else None,
            "phase": u["current_phase"] if u else None,
            "messages_total": u["messages_total"] if u else 0,
            "running_summary": u["running_summary"] if u else None,
            "profile": (
                json.loads(sp["profile_json"])
                if sp and sp["profile_json"]
                else None
            ),
            "procedural": (
                json.loads(pm["memory_json"])
                if pm and pm["memory_json"]
                else None
            ),
        }

    # 3. Группировка по юзерам -> сессии (gap > 30 мин)
    result = {"date": yesterday, "users": []}
    by_user = {}
    for m in messages:
        tid = m["telegram_id"]
        by_user.setdefault(tid, []).append(dict(m))

    for tid, msgs in by_user.items():
        sessions = split_sessions(msgs, gap_minutes=30)
        result["users"].append({
            "telegram_id": tid,
            "context": users.get(tid, {}),
            "sessions": sessions,
        })

    # 4. Аномалии
    result["anomalies"] = detect_anomalies(conn, yesterday)

    conn.close()
    return result


def split_sessions(messages, gap_minutes=30):
    """Разбивает на сессии по паузам > gap_minutes."""
    sessions, current = [], []
    prev_created = None
    for msg in messages:
        curr_created = msg["created_at"]
        if current and prev_created:
            prev_time = datetime.fromisoformat(
                prev_created.replace("Z", "")
            )
            curr_time = datetime.fromisoformat(
                curr_created.replace("Z", "")
            )
            if (curr_time - prev_time).total_seconds() > gap_minutes * 60:
                sessions.append(current)
                current = []
        current.append({
            "role": msg["role"],
            "content": msg["content"],
            "time": curr_created,
        })
        prev_created = curr_created
    if current:
        sessions.append(current)
    return sessions


def detect_anomalies(conn, date):
    """SQL-проверки без LLM."""
    anomalies = []

    # Fallback-ответы
    fallbacks = [
        "Мм, мне нужно немного подумать. Напиши ещё раз через минутку?",
        "Что-то я задумалась. Попробуй ещё раз?",
        "Ой, мысль потерялась. Напиши ещё раз?",
    ]
    placeholders = ",".join("?" * len(fallbacks))
    cnt = conn.execute(
        f"""SELECT COUNT(*) FROM messages
        WHERE role='assistant' AND content IN ({placeholders})
        AND DATE(created_at) = ?""",
        (*fallbacks, date),
    ).fetchone()[0]
    if cnt > 0:
        anomalies.append(f"Fallback-ответов: {cnt}")

    # Профили без данных (юзер > 10 msg, профиль пуст)
    empty = conn.execute("""
        SELECT u.name, u.telegram_id, u.messages_total FROM users u
        LEFT JOIN semantic_profiles sp ON u.telegram_id = sp.telegram_id
        WHERE u.messages_total > 10
        AND (sp.profile_json IS NULL OR sp.profile_json = '{}')
    """).fetchall()
    for e in empty:
        anomalies.append(
            f"Пустой профиль: {e['name'] or '?'} ({e['messages_total']} msg)"
        )

    # Очень длинные ответы (>500 символов)
    long_cnt = conn.execute("""
        SELECT COUNT(*) FROM messages
        WHERE role='assistant' AND LENGTH(content) > 500
        AND DATE(created_at) = ?
    """, (date,)).fetchone()[0]
    if long_cnt > 0:
        anomalies.append(f"Длинных ответов (>500 символов): {long_cnt}")

    # Кризисы
    crises = conn.execute("""
        SELECT COUNT(*) FROM messages
        WHERE source='crisis' AND DATE(created_at) = ?
    """, (date,)).fetchone()[0]
    if crises > 0:
        anomalies.append(f"Кризисных ответов: {crises}")

    # Память не обновлена
    stale = conn.execute("""
        SELECT u.name FROM users u
        WHERE u.needs_full_update = 1
        AND u.last_message_at < datetime('now', '-2 hours')
    """).fetchall()
    for s in stale:
        anomalies.append(f"Память не обновлена: {s['name'] or '?'}")

    return anomalies


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "/tmp/nastavnik_analysis.db"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sessions.json"
    data = extract(db)
    with open(out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(
        f"Extracted: {len(data['users'])} users, "
        f"{sum(len(u['sessions']) for u in data['users'])} sessions, "
        f"{len(data['anomalies'])} anomalies"
    )
