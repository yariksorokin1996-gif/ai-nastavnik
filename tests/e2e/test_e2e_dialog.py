"""E2E тесты диалога: E2E-1, E2E-2, E2E-3.

E2E-1: Первое сообщение нового пользователя.
E2E-2: Полное обновление памяти после паузы.
E2E-3: Фазовый переход ЗНАКОМСТВО → ЗЕРКАЛО.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from bot.memory.database import (
    get_episode_headers,
    get_recent_messages,
    get_user,
    is_message_processed,
    update_user,
)
from bot.memory.full_memory_update import run_full_memory_update
from bot.memory.profile_manager import create_empty_profile
from bot.session_manager import _check_phase_transition, process_message
from tests.e2e.conftest import E2E_TELEGRAM_ID, send_messages, time_ago


# ===========================================================================
# E2E-1: Первое сообщение
# ===========================================================================


class TestE2E1FirstMessage:
    """Новый пользователь пишет 'Привет' → Ева отвечает с 1 вопросом, без 'Алекс'."""

    @pytest.mark.asyncio
    async def test_first_message_full_pipeline(self, e2e_user, mock_llm):
        """E2E-1: process_message → ответ + БД обновлена."""
        mock_llm["session_manager_claude"].return_value = (
            "Привет, Маша! Расскажи, что у тебя сейчас происходит?"
        )

        response = await process_message(
            telegram_id=E2E_TELEGRAM_ID,
            message_id=1,
            text="Привет",
            user_name="Маша",
        )

        # Ответ есть и не содержит "Алекс"
        assert response is not None
        assert "Алекс" not in response
        assert "?" in response

        # БД: пользователь обновлён
        user = await get_user(E2E_TELEGRAM_ID)
        assert user["messages_total"] == 1

        # БД: 2 записи в messages (user + assistant)
        recent = await get_recent_messages(E2E_TELEGRAM_ID, limit=10)
        assert len(recent) == 2
        assert recent[0]["role"] == "user"
        assert recent[1]["role"] == "assistant"

        # Идемпотентность: повторный вызов → None
        assert await is_message_processed(1) is True
        dup = await process_message(E2E_TELEGRAM_ID, 1, "Привет", "Маша")
        assert dup is None


# ===========================================================================
# E2E-2: Полное обновление памяти
# ===========================================================================


class TestE2E2FullMemoryUpdate:
    """5 сообщений → пауза 30 мин → run_full_memory_update → episode создан."""

    @pytest.mark.asyncio
    async def test_full_memory_update_creates_episode(self, e2e_user, mock_llm):
        """E2E-2: после паузы full_memory_update создаёт эпизод и обновляет профиль."""

        # GPT mock для episode_manager.create_episode
        episode_summary = json.dumps({
            "title": "Первый разговор",
            "summary": "Маша рассказала о себе",
            "emotional_tone": "тёплый",
            "key_insight": None,
            "commitments": [],
            "techniques_worked": ["отражение"],
            "techniques_failed": [],
        })

        profile_diff = json.dumps({
            "set_fields": {"city": "Москва"},
            "add_to_lists": {},
            "remove_fields": [],
        })

        # episode_manager использует call_gpt для create_episode и find_relevant
        mock_llm["episode_manager_gpt"].return_value = episode_summary
        # full_memory_update использует call_gpt для profile update
        mock_llm["full_memory_update_gpt"].return_value = profile_diff

        # Создаём пустой профиль (create_user не создаёт его)
        await create_empty_profile(E2E_TELEGRAM_ID)

        # Отправить 4 сообщения (не 5 — иначе % 5 == 0 триггерит фоновый update)
        await send_messages(E2E_TELEGRAM_ID, 4, mock_llm["session_manager_claude"])

        # Инжектируем паузу: last_message_at = 35 мин назад
        await update_user(E2E_TELEGRAM_ID, last_message_at=time_ago(35), needs_full_update=1)

        # Запускаем полное обновление
        results = await run_full_memory_update()

        # Проверяем результат
        assert len(results) >= 1
        result = results[0]
        assert result.telegram_id == E2E_TELEGRAM_ID
        assert result.episode_id is not None
        assert result.error is None or result.error == ""

        # БД: эпизод создан
        headers = await get_episode_headers(E2E_TELEGRAM_ID)
        assert len(headers) >= 1

        # БД: needs_full_update сброшен
        user = await get_user(E2E_TELEGRAM_ID)
        assert user["needs_full_update"] == 0


# ===========================================================================
# E2E-3: Фазовый переход
# ===========================================================================


class TestE2E3PhaseTransition:
    """messages_total=9 → 1 сообщение → _check_phase_transition → ЗЕРКАЛО."""

    @pytest.mark.asyncio
    async def test_phase_advances_to_zerkalo(self, e2e_user, mock_llm, monkeypatch):
        """E2E-3: при advance рекомендации фаза меняется ЗНАКОМСТВО → ЗЕРКАЛО."""

        # Выставляем messages_total=9, фаза ЗНАКОМСТВО
        await update_user(
            E2E_TELEGRAM_ID,
            messages_total=9,
            current_phase="ЗНАКОМСТВО",
        )

        # GPT mock для phase_evaluator: advance с высокой уверенностью
        mock_llm["phase_evaluator_gpt"].return_value = json.dumps({
            "recommendation": "advance",
            "confidence": 0.85,
            "criteria_met": ["Знает имя", "Упомянула проблему"],
        })

        # Подавляем фоновый create_task (иначе двойной вызов _check_phase_transition)
        monkeypatch.setattr(
            "bot.session_manager.asyncio.create_task",
            lambda coro: coro.close(),
        )

        # Отправляем 10-е сообщение → messages_total станет 10, 10%10==0
        response = await process_message(
            telegram_id=E2E_TELEGRAM_ID,
            message_id=10,
            text="Я хочу рассказать тебе подробнее о себе",
            user_name="Маша",
        )
        assert response is not None

        # Вызываем _check_phase_transition напрямую (контролируемый вызов)
        await _check_phase_transition(E2E_TELEGRAM_ID, messages_total=10)

        # Проверяем: фаза сменилась
        user = await get_user(E2E_TELEGRAM_ID)
        assert user["current_phase"] == "ЗЕРКАЛО"

        # Проверяем: запись в phase_transitions
        from bot.memory.database import get_db
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM phase_transitions WHERE telegram_id = ?",
                (E2E_TELEGRAM_ID,),
            ) as cur:
                transitions = [dict(r) for r in await cur.fetchall()]

        assert len(transitions) >= 1
        assert transitions[-1]["from_phase"] == "ЗНАКОМСТВО"
        assert transitions[-1]["to_phase"] == "ЗЕРКАЛО"
