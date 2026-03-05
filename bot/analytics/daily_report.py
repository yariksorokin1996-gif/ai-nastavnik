"""Ежедневный отчёт владельцу (12 метрик за вчера)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from bot.memory.database import get_db
from shared.config import OWNER_TELEGRAM_ID

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3))


async def generate_daily_report(context) -> None:
    """APScheduler job: отправляет ежедневный отчёт в 09:00 MSK."""
    if not OWNER_TELEGRAM_ID:
        logger.warning("daily_report: OWNER_TELEGRAM_ID=0, skip")
        return

    bot = context.bot
    text = await _build_report()

    try:
        await bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text)
    except Exception:
        logger.error("daily_report: failed to send", exc_info=True)


async def _build_report() -> str:
    """Собирает 12 метрик из БД за вчера."""
    sections: list[str] = []
    yesterday = datetime.now(MOSCOW_TZ).date() - timedelta(days=1)
    header = f"\U0001f4ca \u041e\u0442\u0447\u0451\u0442 \u0437\u0430 {yesterday.strftime('%d.%m.%Y')}\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
    sections.append(header)

    async with get_db() as db:
        # 1. Активные юзеры
        try:
            async with db.execute(
                """SELECT DISTINCT u.name, u.telegram_id FROM users u
                   JOIN messages m ON u.telegram_id = m.telegram_id
                   WHERE m.role = 'user' AND DATE(m.created_at) = DATE('now', '-1 day')"""
            ) as cursor:
                active = [dict(r) for r in await cursor.fetchall()]
            async with db.execute("SELECT COUNT(*) FROM users") as cursor2:
                total = (await cursor2.fetchone())[0]
            names = ", ".join(r["name"] or "?" for r in active[:7])
            if len(active) > 7:
                names += "..."
            sections.append(f"\U0001f465 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435: {len(active)}/{total} ({names})")
        except Exception:
            sections.append("\U0001f465 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 2. Сообщений
        try:
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'user' AND DATE(created_at) = DATE('now', '-1 day')"
            ) as cursor:
                msgs_today = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'user' AND DATE(created_at) = DATE('now', '-2 days')"
            ) as cursor:
                msgs_prev = (await cursor.fetchone())[0]
            pct = ""
            if msgs_prev > 0:
                change = round((msgs_today - msgs_prev) / msgs_prev * 100)
                pct = f" ({'+' if change >= 0 else ''}{change}%)"
            sections.append(f"\U0001f4ac \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439: {msgs_today}{pct}")
        except Exception:
            sections.append("\U0001f4ac \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 3. Разбивка по source + голосовые
        try:
            async with db.execute(
                """SELECT source, COUNT(*) as cnt FROM messages
                   WHERE role = 'user' AND DATE(created_at) = DATE('now', '-1 day')
                   GROUP BY source"""
            ) as cursor:
                by_source = {r["source"]: r["cnt"] for r in await cursor.fetchall()}
            async with db.execute(
                """SELECT COUNT(*) FROM messages
                   WHERE role = 'user' AND is_voice = 1 AND DATE(created_at) = DATE('now', '-1 day')"""
            ) as cursor:
                voice = (await cursor.fetchone())[0]
            user_msgs = by_source.get("user", 0)
            daily = by_source.get("daily_message", 0)
            reminder = by_source.get("silence_reminder", 0)
            sections.append(f"   \u0421\u0430\u043c\u0438: {user_msgs} | Daily: {daily} | Reminder: {reminder} | \u0413\u043e\u043b\u043e\u0441: {voice}")
        except Exception:
            sections.append("   \u0420\u0430\u0437\u0431\u0438\u0432\u043a\u0430: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 4. Молчащие >= 2 дней
        try:
            async with db.execute(
                """SELECT name, telegram_id,
                     CAST((julianday('now') - julianday(last_message_at)) AS INTEGER) as days_silent
                   FROM users WHERE last_message_at < datetime('now', '-2 days')
                   ORDER BY days_silent DESC"""
            ) as cursor:
                silent = [dict(r) for r in await cursor.fetchall()]
            if silent:
                parts = []
                for s in silent:
                    warn = " \u26a0\ufe0f" if s["days_silent"] >= 4 else ""
                    parts.append(f"{s['name'] or '?'} ({s['days_silent']}\u0434{warn})")
                sections.append(f"\U0001f507 \u041c\u043e\u043b\u0447\u0430\u0442: {', '.join(parts)}")
            else:
                sections.append("\U0001f507 \u041c\u043e\u043b\u0447\u0430\u0442: \u043d\u0438\u043a\u0442\u043e")
        except Exception:
            sections.append("\U0001f507 \u041c\u043e\u043b\u0447\u0430\u0442: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        sections.append("")  # пустая строка-разделитель

        # 5. North Star: feeling_after
        try:
            async with db.execute(
                """SELECT feeling_after, COUNT(*) as cnt FROM session_feedback
                   WHERE DATE(created_at) = DATE('now', '-1 day') AND feeling_after IS NOT NULL
                   GROUP BY feeling_after"""
            ) as cursor:
                feelings = {r["feeling_after"]: r["cnt"] for r in await cursor.fetchall()}
            better = feelings.get(1, 0)
            same = feelings.get(2, 0)
            worse = feelings.get(3, 0)
            total_f = better + same + worse
            pct = f" ({round(better / total_f * 100)}% \u00ab\u043b\u0443\u0447\u0448\u0435\u00bb)" if total_f > 0 else ""
            sections.append(f"\U0001f60a \u041d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435: \U0001f7e2{better} / \U0001f7e1{same} / \U0001f534{worse}{pct}")
        except Exception:
            sections.append("\U0001f60a \u041d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 6. Практика
        try:
            async with db.execute(
                """SELECT tried_in_practice, COUNT(*) as cnt FROM session_feedback
                   WHERE DATE(created_at) = DATE('now', '-1 day') AND tried_in_practice IS NOT NULL
                   GROUP BY tried_in_practice"""
            ) as cursor:
                enact = {r["tried_in_practice"]: r["cnt"] for r in await cursor.fetchall()}
            yes = enact.get(1, 0)
            total_e = sum(enact.values())
            sections.append(f"\u2705 \u041f\u0440\u0430\u043a\u0442\u0438\u043a\u0430: {yes}/{total_e} \u043f\u0440\u0438\u043c\u0435\u043d\u0438\u043b\u0438")
        except Exception:
            sections.append("\u2705 \u041f\u0440\u0430\u043a\u0442\u0438\u043a\u0430: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 7. Фазы
        try:
            async with db.execute(
                "SELECT current_phase, COUNT(*) as cnt FROM users GROUP BY current_phase"
            ) as cursor:
                phases = {r["current_phase"]: r["cnt"] for r in await cursor.fetchall()}
            parts = [f"{phase}\u00d7{cnt}" for phase, cnt in phases.items() if phase]
            phases_str = " / ".join(parts) if parts else "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445"
            sections.append(f"\U0001f4c8 \u0424\u0430\u0437\u044b: {phases_str}")
        except Exception:
            sections.append("\U0001f4c8 \u0424\u0430\u0437\u044b: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 8. Цели
        try:
            async with db.execute(
                "SELECT COUNT(*) FROM goal_steps WHERE status = 'completed' AND DATE(completed_at) = DATE('now', '-1 day')"
            ) as cursor:
                completed = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM goal_steps WHERE deadline_at < DATE('now') AND status = 'pending'"
            ) as cursor:
                overdue = (await cursor.fetchone())[0]
            sections.append(f"\U0001f3af \u0426\u0435\u043b\u0438: +{completed} \u0448\u0430\u0433\u043e\u0432, \u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0435\u043d\u043e {overdue}")
        except Exception:
            sections.append("\U0001f3af \u0426\u0435\u043b\u0438: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 9. Webapp
        try:
            async with db.execute(
                """SELECT event_type, COUNT(*) as cnt FROM webapp_events
                   WHERE DATE(created_at) = DATE('now', '-1 day')
                   GROUP BY event_type"""
            ) as cursor:
                wa = {r["event_type"]: r["cnt"] for r in await cursor.fetchall()}
            opens = wa.get("app_open", 0)
            steps = wa.get("step_complete", 0)
            sections.append(f"\U0001f4f1 Webapp: {opens} \u043e\u0442\u043a\u0440\u044b\u0442\u0438\u0439, {steps} \u0448\u0430\u0433\u043e\u0432")
        except Exception:
            sections.append("\U0001f4f1 Webapp: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 10. Daily messages
        try:
            async with db.execute(
                "SELECT COUNT(*) as sent, SUM(responded) as responded FROM daily_messages WHERE DATE(created_at) = DATE('now', '-1 day')"
            ) as cursor:
                row = dict(await cursor.fetchone())
            sent = row["sent"] or 0
            responded = row["responded"] or 0
            pct = f" ({round(responded / sent * 100)}%)" if sent > 0 else ""
            sections.append(f"\U0001f48c Daily: {sent}\u2192{responded}{pct}")
        except Exception:
            sections.append("\U0001f48c Daily: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 11. Latency
        try:
            async with db.execute(
                """SELECT AVG(response_latency_ms) as avg_lat FROM messages
                   WHERE role = 'assistant' AND response_latency_ms IS NOT NULL
                   AND DATE(created_at) = DATE('now', '-1 day')"""
            ) as cursor:
                avg_row = await cursor.fetchone()
            avg_lat = avg_row["avg_lat"] if avg_row else None

            # p95 через OFFSET
            async with db.execute(
                """SELECT COUNT(*) FROM messages
                   WHERE role = 'assistant' AND response_latency_ms IS NOT NULL
                   AND DATE(created_at) = DATE('now', '-1 day')"""
            ) as cursor:
                count = (await cursor.fetchone())[0]
            p95 = None
            if count > 0:
                offset = max(0, int(count * 0.05))
                async with db.execute(
                    """SELECT response_latency_ms FROM messages
                       WHERE role = 'assistant' AND response_latency_ms IS NOT NULL
                       AND DATE(created_at) = DATE('now', '-1 day')
                       ORDER BY response_latency_ms DESC LIMIT 1 OFFSET ?""",
                    (offset,),
                ) as cursor:
                    p95_row = await cursor.fetchone()
                p95 = p95_row[0] if p95_row else None

            avg_s = f"{avg_lat / 1000:.1f}s" if avg_lat else "n/a"
            p95_s = f"{p95 / 1000:.1f}s" if p95 else "n/a"
            sections.append(f"\u26a1 Latency: {avg_s} avg / {p95_s} p95")
        except Exception:
            sections.append("\u26a1 Latency: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # 12. Кризисы (из safety-модуля: source='crisis' в messages)
        try:
            async with db.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE source = 'crisis' AND DATE(created_at) = DATE('now', '-1 day')"""
            ) as cursor:
                row = await cursor.fetchone()
            cnt = row[0] if row else 0
            if cnt > 0:
                sections.append(f"\U0001f6a8 \u041a\u0440\u0438\u0437\u0438\u0441\u043e\u0432: {cnt}")
            else:
                sections.append("\U0001f6a8 \u041a\u0440\u0438\u0437\u0438\u0441\u043e\u0432: 0")
        except Exception:
            sections.append("\U0001f6a8 \u041a\u0440\u0438\u0437\u0438\u0441\u043e\u0432: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

    return "\n".join(sections)
