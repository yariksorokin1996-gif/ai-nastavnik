"""E2E тесты аналитики: E2E-6, E2E-7, E2E-8.

E2E-6: Daily report содержит все 12 секций.
E2E-7: Full pipeline: memory update → ask_feeling → feedback в БД.
E2E-8: Alerter при 3 ошибках build_context.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from bot.analytics.alerter import alerter
from bot.analytics.daily_report import _build_report
from bot.analytics.feedback_collector import ask_feeling
from bot.memory.database import (
    create_user,
    get_db,
    update_user,
)
from bot.memory.full_memory_update import run_full_memory_update
from bot.memory.profile_manager import create_empty_profile
from bot.session_manager import process_message
from tests.e2e.conftest import (
    E2E_TELEGRAM_ID,
    send_messages,
    time_ago,
)


# ===========================================================================
# E2E-6: Daily report
# ===========================================================================


class TestE2E6DailyReport:
    """Inject данные за вчера → _build_report → текст содержит 12 секций."""

    @pytest.mark.asyncio
    async def test_daily_report_all_sections(self):
        """E2E-6: daily report содержит все ключевые метрики."""

        # Создать 2 юзеров
        await create_user(111111, name="Маша")
        await create_user(222222, name="Аня")

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d 12:00:00"
        )

        async with get_db() as db:
            # Сообщения за вчера (user + assistant)
            for i in range(5):
                await db.execute(
                    "INSERT INTO messages (telegram_id, role, content, source, created_at, response_latency_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (111111, "user", f"Сообщение {i}", "user", yesterday, None),
                )
                await db.execute(
                    "INSERT INTO messages (telegram_id, role, content, source, created_at, response_latency_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (111111, "assistant", f"Ответ {i}", "user", yesterday, 3000),
                )

            # episode (нужен для FK в session_feedback)
            await db.execute(
                "INSERT INTO episodes (telegram_id, title, summary, emotional_tone, session_start, session_end, messages_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (111111, "Сессия", "Тест", "нейтральный", yesterday, yesterday, 5, yesterday),
            )
            ep_row = await db.execute("SELECT last_insert_rowid()")
            ep_id = (await ep_row.fetchone())[0]

            # session_feedback
            await db.execute(
                "INSERT INTO session_feedback (telegram_id, episode_id, session_end, messages_in_session, feeling_after, sent, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (111111, ep_id, yesterday, 5, 1, 1, yesterday),
            )

            # goal_steps completed
            # Сначала создаём goal
            await db.execute(
                "INSERT INTO goals (telegram_id, title, status, created_at) VALUES (?, ?, ?, ?)",
                (111111, "Цель", "active", yesterday),
            )
            goal_id_row = await db.execute("SELECT last_insert_rowid()")
            goal_id = (await goal_id_row.fetchone())[0]
            await db.execute(
                "INSERT INTO goal_steps (goal_id, telegram_id, title, status, sort_order, completed_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (goal_id, 111111, "Шаг 1", "completed", 0, yesterday, yesterday),
            )

            # daily_messages
            await db.execute(
                "INSERT INTO daily_messages (telegram_id, message_text, day_number, source, responded, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (111111, "Доброе утро!", 1, "daily_message", 0, yesterday),
            )

            # webapp_events
            await db.execute(
                "INSERT INTO webapp_events (telegram_id, event_type, created_at) VALUES (?, ?, ?)",
                (111111, "app_open", yesterday),
            )
            await db.execute(
                "INSERT INTO webapp_events (telegram_id, event_type, created_at) VALUES (?, ?, ?)",
                (111111, "step_complete", yesterday),
            )

            await db.commit()

        # Генерируем отчёт
        text = await _build_report()

        # Проверяем 12 секций (emoji-маркеры)
        assert "Активные" in text          # 1. Активные юзеры
        assert "Сообщений" in text          # 2. Сообщений
        assert "Сами:" in text              # 3. Разбивка
        assert "Молчат" in text             # 4. Молчащие
        assert "Настроение" in text         # 5. North Star
        assert "Практика" in text           # 6. Практика
        assert "Фазы" in text               # 7. Фазы
        assert "Цели" in text               # 8. Цели
        assert "Webapp" in text             # 9. Webapp
        assert "Daily" in text              # 10. Daily
        assert "Latency" in text            # 11. Latency
        assert "Кризисов" in text           # 12. Кризисы


# ===========================================================================
# E2E-7: Full pipeline (memory → feedback → callback)
# ===========================================================================


class TestE2E7FeedbackPipeline:
    """full_memory_update → ask_feeling → feedback в БД."""

    @pytest.mark.asyncio
    async def test_memory_update_then_feedback(self, e2e_user, mock_llm, mock_bot):
        """E2E-7: обновление памяти создаёт эпизод → ask_feeling → feedback_id."""

        # GPT mock для episode
        mock_llm["episode_manager_gpt"].return_value = json.dumps({
            "title": "Вечерний разговор",
            "summary": "Маша рассказала о работе",
            "emotional_tone": "тёплый",
            "key_insight": "Маша хочет сменить работу",
            "commitments": ["Обновить резюме"],
            "techniques_worked": ["отражение"],
            "techniques_failed": [],
        })
        mock_llm["full_memory_update_gpt"].return_value = json.dumps({
            "set_fields": {"work": "менеджер"},
            "add_to_lists": {},
            "remove_fields": [],
        })

        # Создаём пустой профиль (create_user не создаёт его)
        await create_empty_profile(E2E_TELEGRAM_ID)

        # Отправить 5 сообщений
        await send_messages(E2E_TELEGRAM_ID, 5, mock_llm["session_manager_claude"])

        # Инжектируем паузу 2.5ч для full_memory_update
        await update_user(E2E_TELEGRAM_ID, last_message_at=time_ago(150))

        # Запускаем полное обновление
        results = await run_full_memory_update()
        assert len(results) >= 1
        assert results[0].episode_id is not None
        episode_id = results[0].episode_id

        # Обновим timestamps: сообщения и эпизод = 2.5ч назад
        # (ask_feeling проверяет: юзер НЕ писал после session_end)
        async with get_db() as db:
            await db.execute(
                "UPDATE messages SET created_at = ? WHERE telegram_id = ?",
                (time_ago(155), E2E_TELEGRAM_ID),
            )
            await db.execute(
                "UPDATE episodes SET created_at = ?, session_end = ?, messages_count = 5 WHERE id = ?",
                (time_ago(150), time_ago(150), episode_id),
            )
            await db.commit()

        # Патчим _is_quiet_hours → False
        with patch("bot.analytics.feedback_collector._is_quiet_hours", return_value=False):
            result = await ask_feeling(E2E_TELEGRAM_ID, episode_id, mock_bot)

        assert result is True
        mock_bot.send_message.assert_called_once()

        # Проверяем текст сообщения
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == E2E_TELEGRAM_ID
        assert "лучше" in call_kwargs["text"].lower() or "Стало" in call_kwargs["text"]

        # Проверяем что session_feedback создан в БД
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM session_feedback WHERE telegram_id = ? AND episode_id = ?",
                (E2E_TELEGRAM_ID, episode_id),
            ) as cur:
                feedback_rows = [dict(r) for r in await cur.fetchall()]

        assert len(feedback_rows) >= 1
        assert feedback_rows[0]["sent"] == 1


# ===========================================================================
# E2E-8: Alerter при ошибках build_context
# ===========================================================================


class TestE2E8AlerterOnErrors:
    """3 ошибки build_context → alerter отправляет алерт OWNER_TELEGRAM_ID."""

    @pytest.mark.asyncio
    async def test_alerter_sends_on_threshold(self, e2e_user, mock_llm, mock_bot, monkeypatch):
        """E2E-8: 3 consecutive_empty_context → алерт отправлен."""

        # Инициализируем alerter
        alerter.init(mock_bot)

        # ВАЖНО: патчим OWNER_TELEGRAM_ID в alerter (from-import — локальная копия)
        monkeypatch.setattr("bot.analytics.alerter.OWNER_TELEGRAM_ID", 12345)

        # Патчим build_context → всегда падает
        with patch(
            "bot.session_manager.build_context",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection lost"),
        ):
            # Отправляем 3 сообщения (каждое → build_context fails → alerter.check)
            for i in range(3):
                resp = await process_message(
                    telegram_id=E2E_TELEGRAM_ID,
                    message_id=50 + i,
                    text=f"Сообщение {i + 1}",
                    user_name="Маша",
                )
                # Ответ = fallback (не None, т.к. ошибка ловится)
                assert resp is not None

        # Проверяем: алерт отправлен
        assert mock_bot.send_message.called
        # Проверяем chat_id и текст
        call_kwargs = mock_bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == 12345
        assert "consecutive_empty_context" in call_kwargs["text"]
