"""Еженедельная сводка с LLM-анализом качества."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from bot.memory import database
from bot.memory.database import get_db
from bot.prompts.memory_prompts import WEEKLY_ANALYSIS_PROMPT
from shared.config import OWNER_TELEGRAM_ID
from shared.llm_client import LLMError, call_gpt

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3))
MAX_MESSAGES_PER_USER = 20


def _anonymize(text: str, user_name: str | None, people: list[dict] | None) -> str:
    """Анонимизирует текст перед отправкой в LLM."""
    if not text:
        return text
    if user_name:
        text = text.replace(user_name, "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c")
    if people:
        for i, person in enumerate(people):
            name = person.get("name", "")
            if name:
                text = text.replace(name, f"[\u0411\u043b\u0438\u0437\u043a\u0438\u0439 {i + 1}]")
    text = re.sub(r'\+?\d[\d\-\s]{9,}', '[\u0422\u0415\u041b\u0415\u0424\u041e\u041d]', text)
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[EMAIL]', text)
    return text


async def generate_weekly_report(context) -> None:
    """APScheduler job: еженедельная сводка (воскресенье 12:00 MSK)."""
    if not OWNER_TELEGRAM_ID:
        logger.warning("weekly_report: OWNER_TELEGRAM_ID=0, skip")
        return

    bot = context.bot
    text = await _build_weekly_report()

    try:
        await bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text)
    except Exception:
        logger.error("weekly_report: failed to send", exc_info=True)


async def _build_weekly_report() -> str:
    """Собирает данные за неделю и запускает LLM-анализ."""
    now = datetime.now(MOSCOW_TZ)
    week_end = now.date()
    week_start = week_end - timedelta(days=7)

    sections: list[str] = []
    sections.append(f"\U0001f4ca \u041d\u0435\u0434\u0435\u043b\u044f ({week_start.strftime('%d.%m')}-{week_end.strftime('%d.%m')})")
    sections.append("\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

    async with get_db() as db:
        # Retention
        try:
            retention = await _calc_retention(db)
            sections.append(
                f"\U0001f4c8 RETENTION: D1: {retention.get('d1', 'n/a')} | "
                f"D3: {retention.get('d3', 'n/a')} | D7: {retention.get('d7', 'n/a')}"
            )
        except Exception:
            sections.append("\U0001f4c8 RETENTION: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

        # North Star
        try:
            async with db.execute(
                """SELECT feeling_after, COUNT(*) as cnt FROM session_feedback
                   WHERE created_at >= datetime('now', '-7 days') AND feeling_after IS NOT NULL
                   GROUP BY feeling_after"""
            ) as cursor:
                feelings = {r["feeling_after"]: r["cnt"] for r in await cursor.fetchall()}
            better = feelings.get(1, 0)
            total = sum(feelings.values())
            pct = round(better / total * 100) if total > 0 else 0
            sections.append(f"\U0001f60a NORTH STAR: {pct}% \u00ab\u0441\u0442\u0430\u043b\u043e \u043b\u0443\u0447\u0448\u0435\u00bb")
        except Exception:
            sections.append("\U0001f60a NORTH STAR: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

    # LLM-анализ per user (отдельные get_db вызовы внутри)
    try:
        llm_analysis = await _run_llm_analysis()
        if llm_analysis:
            sections.append("")
            sections.extend(llm_analysis)
        else:
            sections.append("\n\U0001f916 LLM-\u0430\u043d\u0430\u043b\u0438\u0437: \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445")
    except LLMError:
        sections.append("\n\U0001f916 LLM-\u0430\u043d\u0430\u043b\u0438\u0437: \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d (LLM \u043e\u0448\u0438\u0431\u043a\u0430)")
    except Exception:
        logger.error("weekly_report: LLM analysis failed", exc_info=True)
        sections.append("\n\U0001f916 LLM-\u0430\u043d\u0430\u043b\u0438\u0437: --- \u041e\u0448\u0438\u0431\u043a\u0430 ---")

    # Сохраняем в БД
    try:
        await database.save_weekly_report(
            week_start=str(week_start),
            week_end=str(week_end),
            report_json={"sections": sections},
        )
    except Exception:
        logger.error("weekly_report: failed to save to DB", exc_info=True)

    return "\n".join(sections)


async def _calc_retention(db) -> dict:
    """Считает retention D1, D3, D7."""
    result = {}
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        total = (await cursor.fetchone())[0]
    if total == 0:
        return {"d1": "0/0", "d3": "0/0", "d7": "0/0"}

    for label, days in [("d1", 1), ("d3", 3), ("d7", 7)]:
        async with db.execute(
            """SELECT COUNT(DISTINCT telegram_id) FROM messages
                WHERE role = 'user'
                AND created_at >= datetime('now', ? || ' days')""",
            (f"-{days}",),
        ) as cursor:
            active = (await cursor.fetchone())[0]
        result[label] = f"{active}/{total} ({round(active / total * 100)}%)"
    return result


async def _run_llm_analysis() -> list[str]:
    """Запускает LLM-анализ по каждому юзеру, агрегирует."""
    async with get_db() as db:
        async with db.execute("SELECT telegram_id, name FROM users") as cursor:
            users = [dict(r) for r in await cursor.fetchall()]

    if not users:
        return []

    all_hits: list[str] = []
    all_fails: list[str] = []
    all_recommendations: list[str] = []

    for user in users:
        tid = user["telegram_id"]
        name = user.get("name") or "?"

        # Собрать сообщения за неделю
        async with get_db() as db:
            async with db.execute(
                """SELECT role, content, created_at FROM messages
                   WHERE telegram_id = ? AND created_at >= datetime('now', '-7 days')
                   ORDER BY created_at
                   LIMIT ?""",
                (tid, MAX_MESSAGES_PER_USER),
            ) as cursor:
                msgs = [dict(r) for r in await cursor.fetchall()]

        if not msgs:
            continue

        # Получить people из semantic_profiles для анонимизации
        people: list[dict] = []
        try:
            profile_data = await database.get_profile(tid)
            if profile_data and profile_data.get("profile_json"):
                profile = profile_data["profile_json"]
                # get_profile уже парсит JSON в dict
                if isinstance(profile, dict):
                    people = profile.get("people", [])
        except Exception:
            pass

        # Форматируем сессии
        sessions_text = ""
        for m in msgs:
            role = "user" if m["role"] == "user" else "assistant"
            content = _anonymize(m["content"] or "", name, people)
            sessions_text += f"{role}: {content}\n"

        # Вызов LLM
        try:
            prompt = WEEKLY_ANALYSIS_PROMPT.format(sessions_text=sessions_text)
            response = await call_gpt(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            analysis = json.loads(response)

            for session in analysis.get("sessions", []):
                hit = session.get("top_hit")
                if hit:
                    all_hits.append(f"{name}: {hit}")
                fail = session.get("top_fail")
                if fail:
                    all_fails.append(f"{name}: {fail}")

            rec = analysis.get("recommendation")
            if rec:
                all_recommendations.append(rec)

        except (LLMError, json.JSONDecodeError, KeyError) as e:
            logger.warning("weekly LLM analysis failed for user %s: %s", tid, e)
            continue

    # Агрегация
    result: list[str] = []
    if all_hits:
        result.append("\U0001f3c6 \u0422\u041e\u041f \u041f\u041e\u041f\u0410\u0414\u0410\u041d\u0418\u042f:")
        for hit in all_hits[:3]:
            result.append(f"  \u2022 {hit}")
    if all_fails:
        result.append("\U0001f494 \u0422\u041e\u041f \u041f\u0420\u041e\u0412\u0410\u041b\u0410:")
        for fail in all_fails[:3]:
            result.append(f"  \u2022 {fail}")
    if all_recommendations:
        result.append("\U0001f52e \u0420\u0415\u041a\u041e\u041c\u0415\u041d\u0414\u0410\u0426\u0418\u0418:")
        for rec in all_recommendations[:3]:
            result.append(f"  \u2022 {rec}")

    return result
