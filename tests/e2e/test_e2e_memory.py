"""E2E тесты памяти Евы — 20 сценариев.

Блоки:
    A (5): мини-обновление regex (pending_facts, emotion_log)
    B (5): полное обновление (episode, running_summary, profile, cleanup)
    C (5): контекст (profile, summary, episodes, procedural, pause в system_prompt)
    D (3): полный pipeline (send → mini → full → context)
    E (2): edge cases (idempotency, summary compression)
"""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from bot.memory.database import (
    add_message,
    add_pending_fact,
    clear_pending_facts,
    get_pending_facts,
    get_recent_emotions,
    get_running_summary,
    get_episode_headers,
    get_recent_messages,
    get_user,
    save_running_summary,
    update_user,
    upsert_procedural,
)
from bot.memory.full_memory_update import update_single_user
from bot.memory.context_builder import build_context
from bot.memory.profile_manager import (
    create_empty_profile,
    get_profile,
    update_profile,
)
from bot.memory.procedural_memory import get_procedural
from bot.session_manager import _mini_memory_update, process_message
from shared.models import ProfileDiff
from tests.e2e.conftest import E2E_TELEGRAM_ID, send_messages, time_ago

TID = E2E_TELEGRAM_ID


# ===========================================================================
# Блок A: Мини-обновление regex
# ===========================================================================


class TestBlockA_MiniUpdate:
    """A1-A5: _mini_memory_update → pending_facts / emotion_log."""

    @pytest.mark.asyncio
    async def test_a1_person_name(self, e2e_user):
        """A1: 'моя Катя' → pending_fact(person, Катя)."""
        # regex: мо[йяиюей] + Имя — работает с маленькой "мо"
        await _mini_memory_update(TID, "А моя Катя вчера опять пришла поздно", "")

        facts = await get_pending_facts(TID)
        person_facts = [f for f in facts if f["fact_type"] == "person"]
        assert len(person_facts) >= 1
        assert any(f["content"] == "Катя" for f in person_facts)

    @pytest.mark.asyncio
    async def test_a2_age(self, e2e_user):
        """A2: 'Мне 28 лет' → pending_fact(age, 28, high)."""
        await _mini_memory_update(TID, "Мне 28 лет, и я уже устала от этого", "")

        facts = await get_pending_facts(TID)
        age_facts = [f for f in facts if f["fact_type"] == "age"]
        assert len(age_facts) == 1
        assert age_facts[0]["content"] == "28"
        assert age_facts[0]["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_a3_commitment(self, e2e_user):
        """A3: 'Завтра попробую поговорить с мамой' → pending_fact(commitment)."""
        await _mini_memory_update(
            TID, "Завтра попробую поговорить с мамой.", ""
        )

        facts = await get_pending_facts(TID)
        commit_facts = [f for f in facts if f["fact_type"] == "commitment"]
        assert len(commit_facts) >= 1
        assert any("поговорить с мамой" in f["content"] for f in commit_facts)

    @pytest.mark.asyncio
    async def test_a4_emotion(self, e2e_user):
        """A4: 'Мне так грустно, я плачу' → emotion_log(грусть)."""
        await _mini_memory_update(TID, "Мне так грустно, я плачу", "")

        emotions = await get_recent_emotions(TID, limit=5)
        assert len(emotions) >= 1
        assert any(e["emotion"] == "грусть" for e in emotions)

    @pytest.mark.asyncio
    async def test_a5_stoplist_no_false_positive(self, e2e_user):
        """A5: 'Моя Россия', 'Моя Тревога' → НЕ попадают в pending_facts."""
        await _mini_memory_update(TID, "Моя Россия — странная страна", "")
        await _mini_memory_update(TID, "Моя Москва меня утомляет", "")

        facts = await get_pending_facts(TID)
        person_facts = [f for f in facts if f["fact_type"] == "person"]
        names = [f["content"] for f in person_facts]
        assert "Россия" not in names
        assert "Москва" not in names


# ===========================================================================
# Блок B: Полное обновление
# ===========================================================================


class TestBlockB_FullUpdate:
    """B1-B5: send_messages + update_single_user → episode, summary, profile."""

    @pytest.mark.asyncio
    async def test_b1_needs_full_update_flag(self, e2e_user, mock_llm):
        """B1: После сообщений → needs_full_update=1 в БД."""
        # Отправляем 3 msg (не 10, чтобы не триггерить fire-and-forget update)
        await send_messages(TID, 3, mock_llm["session_manager_claude"])

        user = await get_user(TID)
        assert user["messages_total"] == 3
        # process_message ставит needs_full_update=1 на каждом сообщении (Step 14)
        assert user["needs_full_update"] == 1

    @pytest.mark.asyncio
    async def test_b2_episode_created(self, e2e_user, mock_llm):
        """B2: update_single_user → episode создан в БД."""
        episode_json = json.dumps({
            "title": "Первый разговор",
            "summary": "Маша рассказала о своей работе",
            "emotional_tone": "тёплый → заинтересованный",
            "key_insight": None,
            "commitments": [],
            "techniques_worked": ["отражение"],
            "techniques_failed": [],
        })
        mock_llm["episode_manager_gpt"].return_value = episode_json

        # Нужны сообщения в БД для update_single_user
        await send_messages(TID, 4, mock_llm["session_manager_claude"])
        await update_single_user(TID)

        headers = await get_episode_headers(TID)
        assert len(headers) >= 1
        assert headers[0]["title"] == "Первый разговор"

    @pytest.mark.asyncio
    async def test_b3_running_summary_updated(self, e2e_user, mock_llm):
        """B3: update_single_user → running_summary обновлён."""
        summary_text = "ФАКТЫ: Маша — дизайнер из Питера.\nЭМОЦИИ: спокойная.\nДИНАМИКА: открывается."
        episode_json = json.dumps({
            "title": "Разговор", "summary": "...",
            "emotional_tone": "спокойный", "key_insight": None,
            "commitments": [], "techniques_worked": [], "techniques_failed": [],
        })

        # full_memory_update_gpt вызывается дважды: running_summary + profile_diff
        mock_llm["full_memory_update_gpt"].side_effect = [
            summary_text,  # running summary
            '{"set_fields": {}, "add_to_lists": {}, "remove_fields": []}',  # profile
        ]
        mock_llm["episode_manager_gpt"].return_value = episode_json

        await send_messages(TID, 4, mock_llm["session_manager_claude"])
        await update_single_user(TID)

        saved = await get_running_summary(TID)
        assert "Маша" in saved
        assert "дизайнер" in saved

    @pytest.mark.asyncio
    async def test_b4_profile_enriched(self, e2e_user, mock_llm):
        """B4: update_single_user с profile diff → profile обновлён."""
        await create_empty_profile(TID)

        episode_json = json.dumps({
            "title": "Разговор", "summary": "...",
            "emotional_tone": "спокойный", "key_insight": None,
            "commitments": [], "techniques_worked": [], "techniques_failed": [],
        })
        profile_diff = json.dumps({
            "set_fields": {"city": "Питер", "work": "дизайнер"},
            "add_to_lists": {},
            "remove_fields": [],
        })

        mock_llm["episode_manager_gpt"].return_value = episode_json
        mock_llm["full_memory_update_gpt"].side_effect = [
            "Running summary текст",  # running summary
            profile_diff,  # profile
        ]

        await send_messages(TID, 4, mock_llm["session_manager_claude"])
        await update_single_user(TID)

        profile = await get_profile(TID)
        assert profile is not None
        assert profile.city == "Питер"
        assert profile.work == "дизайнер"

    @pytest.mark.asyncio
    async def test_b5_pending_facts_cleared(self, e2e_user, mock_llm):
        """B5: pending_facts очищаются после update_single_user."""
        # Добавляем факты вручную
        await add_pending_fact(TID, "age", "28", "high")
        await add_pending_fact(TID, "person", "Саша", "medium")
        await add_pending_fact(TID, "commitment", "поговорить с мамой", "medium")

        facts_before = await get_pending_facts(TID)
        assert len(facts_before) == 3

        episode_json = json.dumps({
            "title": "Разговор", "summary": "...",
            "emotional_tone": "спокойный", "key_insight": None,
            "commitments": [], "techniques_worked": [], "techniques_failed": [],
        })
        mock_llm["episode_manager_gpt"].return_value = episode_json
        mock_llm["full_memory_update_gpt"].side_effect = [
            "Summary",
            '{"set_fields": {}, "add_to_lists": {}, "remove_fields": []}',
        ]

        await send_messages(TID, 3, mock_llm["session_manager_claude"])
        await update_single_user(TID)

        facts_after = await get_pending_facts(TID)
        assert len(facts_after) == 0


# ===========================================================================
# Блок C: Контекст (build_context)
# ===========================================================================


class TestBlockC_Context:
    """C1-C5: заполняем БД → build_context → проверяем system_prompt."""

    @pytest.mark.asyncio
    async def test_c1_profile_in_context(self, e2e_user, mock_llm):
        """C1: Profile с city/work → попадает в system_prompt."""
        await create_empty_profile(TID)
        diff = ProfileDiff(
            set_fields={"name": "Маша", "city": "Москва", "work": "дизайнер"},
            add_to_lists={},
            remove_fields=[],
        )
        await update_profile(TID, diff)

        # Нужно хотя бы 1 сообщение чтобы build_context работал
        await add_message(TID, "user", "Привет", source="user")

        system_prompt, _, meta = await build_context(TID, "Привет")
        assert "Маша" in system_prompt
        assert "Москва" in system_prompt
        assert "дизайнер" in system_prompt

    @pytest.mark.asyncio
    async def test_c2_running_summary_in_context(self, e2e_user, mock_llm):
        """C2: running_summary → попадает в system_prompt."""
        await save_running_summary(
            TID, "ФАКТЫ: Маша поссорилась с подругой Катей из-за денег."
        )
        await add_message(TID, "user", "Привет", source="user")

        system_prompt, _, _ = await build_context(TID, "Привет")
        assert "поссорилась" in system_prompt
        assert "Катей" in system_prompt

    @pytest.mark.asyncio
    async def test_c3_episodes_in_context(self, e2e_user, mock_llm):
        """C3: Эпизод в БД → попадает в system_prompt через find_relevant_episodes."""
        from bot.memory.database import create_episode as db_create_episode

        await db_create_episode(
            telegram_id=TID,
            title="Конфликт на работе",
            summary="Маша поссорилась с начальником из-за дедлайна",
            emotional_tone="злость → принятие",
            key_insight="Маша боится конфликтов",
            commitments_json=["поговорить с HR"],
            techniques_worked_json=["отражение"],
            techniques_failed_json=[],
            messages_count=10,
        )

        # Мок: выбрать этот эпизод (selected = 1-based номер в списке)
        mock_llm["episode_manager_gpt"].return_value = json.dumps(
            {"selected": [1]}
        )
        await add_message(TID, "user", "На работе опять проблемы", source="user")

        system_prompt, _, meta = await build_context(TID, "На работе опять проблемы")
        assert "Конфликт на работе" in system_prompt
        assert "начальником" in system_prompt

    @pytest.mark.asyncio
    async def test_c4_procedural_in_context(self, e2e_user, mock_llm):
        """C4: procedural_memory → попадает в system_prompt."""
        await upsert_procedural(
            TID,
            {
                "what_works": ["отражение", "мягкие вопросы"],
                "what_doesnt": ["прямые советы"],
                "communication_style": {"tone": "тёплый"},
            },
            tokens_count=50,
        )
        await add_message(TID, "user", "Привет", source="user")

        system_prompt, _, _ = await build_context(TID, "Привет")
        assert "отражение" in system_prompt
        assert "прямые советы" in system_prompt

    @pytest.mark.asyncio
    async def test_c5_pause_in_context(self, e2e_user, mock_llm):
        """C5: Пауза > 60 минут → 'Пауза' в system_prompt."""
        await update_user(TID, last_message_at=time_ago(120))
        await add_message(TID, "user", "Привет", source="user")

        system_prompt, _, _ = await build_context(TID, "Привет")
        assert "Пауза" in system_prompt or "пауз" in system_prompt.lower()


# ===========================================================================
# Блок D: Полный pipeline
# ===========================================================================


class TestBlockD_FullPipeline:
    """D1-D3: send → mini → full → context."""

    @pytest.mark.asyncio
    async def test_d1_full_cycle_profile_in_context(self, e2e_user, mock_llm, monkeypatch):
        """D1: 9 msg → manual full_update → build_context содержит profile данные."""
        # Подавляем фоновые задачи (иначе _trigger_memory_update расходует side_effect)
        monkeypatch.setattr(
            "bot.session_manager.asyncio.create_task",
            lambda coro: coro.close(),
        )

        await create_empty_profile(TID)

        episode_json = json.dumps({
            "title": "Знакомство", "summary": "Маша — дизайнер из Питера",
            "emotional_tone": "тёплый", "key_insight": None,
            "commitments": [], "techniques_worked": ["отражение"],
            "techniques_failed": [],
        })
        profile_diff = json.dumps({
            "set_fields": {"city": "Питер", "work": "дизайнер"},
            "add_to_lists": {},
            "remove_fields": [],
        })
        mock_llm["episode_manager_gpt"].return_value = episode_json
        mock_llm["full_memory_update_gpt"].side_effect = [
            "ФАКТЫ: дизайнер из Питера",  # running summary
            profile_diff,  # profile
        ]

        # 9 msg (не 5) чтобы не триггерить fire-and-forget update
        texts = [
            "Привет!", "Я дизайнер", "Живу в Питере",
            "Работаю в агентстве", "Мне нравится моя работа",
            "Но иногда устаю", "Особенно от дедлайнов",
            "Мой муж Дима помогает", "Он меня поддерживает",
        ]
        await send_messages(TID, 9, mock_llm["session_manager_claude"], texts=texts)
        await update_single_user(TID)

        system_prompt, _, _ = await build_context(TID, "Как дела?")
        assert "Питер" in system_prompt
        assert "дизайнер" in system_prompt

    @pytest.mark.asyncio
    async def test_d2_mini_to_full_to_profile(self, e2e_user, mock_llm):
        """D2: mini_update → pending_facts → full_update → profile."""
        await create_empty_profile(TID)

        # Отправляем сообщение с возрастом и именем
        await process_message(TID, 1, "Мне 28 лет, мой Саша такой хороший", "Маша")

        # Ждём mini_update (fire-and-forget) — даём asyncio шанс выполнить
        await asyncio.sleep(0.1)

        # Проверяем pending_facts
        facts = await get_pending_facts(TID)
        fact_types = [f["fact_type"] for f in facts]
        assert "age" in fact_types
        assert "person" in fact_types

        # Теперь full update использует эти факты
        episode_json = json.dumps({
            "title": "Разговор", "summary": "...",
            "emotional_tone": "тёплый", "key_insight": None,
            "commitments": [], "techniques_worked": [], "techniques_failed": [],
        })
        mock_llm["episode_manager_gpt"].return_value = episode_json
        mock_llm["full_memory_update_gpt"].side_effect = [
            "Summary",
            json.dumps({
                "set_fields": {"age": 28},
                "add_to_lists": {},
                "remove_fields": [],
            }),
        ]
        await update_single_user(TID)

        profile = await get_profile(TID)
        assert profile is not None
        assert profile.age == 28

        # pending_facts очищены
        facts_after = await get_pending_facts(TID)
        assert len(facts_after) == 0

    @pytest.mark.asyncio
    async def test_d3_contradictory_facts_replaced(self, e2e_user, mock_llm):
        """D3: profile.work=дизайнер → update с work=фрилансер → заменяется."""
        await create_empty_profile(TID)
        diff = ProfileDiff(
            set_fields={"work": "дизайнер"},
            add_to_lists={},
            remove_fields=[],
        )
        await update_profile(TID, diff)

        profile_before = await get_profile(TID)
        assert profile_before.work == "дизайнер"

        # Full update заменяет work
        episode_json = json.dumps({
            "title": "Разговор", "summary": "...",
            "emotional_tone": "спокойный", "key_insight": None,
            "commitments": [], "techniques_worked": [], "techniques_failed": [],
        })
        mock_llm["episode_manager_gpt"].return_value = episode_json
        mock_llm["full_memory_update_gpt"].side_effect = [
            "Summary",
            json.dumps({
                "set_fields": {"work": "фрилансер"},
                "add_to_lists": {},
                "remove_fields": [],
            }),
        ]
        await send_messages(TID, 3, mock_llm["session_manager_claude"])
        await update_single_user(TID)

        profile_after = await get_profile(TID)
        assert profile_after.work == "фрилансер"


# ===========================================================================
# Блок E: Edge cases
# ===========================================================================


class TestBlockE_EdgeCases:
    """E1-E2: idempotency, summary compression."""

    @pytest.mark.asyncio
    async def test_e1_idempotency(self, e2e_user, mock_llm):
        """E1: Повторное сообщение с тем же message_id → None, без дублей в БД."""
        resp1 = await process_message(TID, 42, "Привет", "Маша")
        assert resp1 is not None

        resp2 = await process_message(TID, 42, "Привет", "Маша")
        assert resp2 is None

        messages = await get_recent_messages(TID, limit=10)
        # Только 2 записи: user + assistant (не 4)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_e2_running_summary_compression(self, e2e_user, mock_llm):
        """E2: Running summary > 400 слов → сжимается через COMPRESS_PROMPT."""
        long_summary = " ".join(["слово"] * 500)
        await save_running_summary(TID, long_summary)

        episode_json = json.dumps({
            "title": "Разговор", "summary": "...",
            "emotional_tone": "спокойный", "key_insight": None,
            "commitments": [], "techniques_worked": [], "techniques_failed": [],
        })
        compressed = "ФАКТЫ: краткое содержание. ЭМОЦИИ: спокойная. ДИНАМИКА: стабильная."

        # full_memory_update_gpt вызывается: running_summary → compress → profile
        mock_llm["full_memory_update_gpt"].side_effect = [
            long_summary,  # первый вызов: running summary (> 400 слов)
            compressed,  # второй вызов: compress
            '{"set_fields": {}, "add_to_lists": {}, "remove_fields": []}',  # profile
        ]
        mock_llm["episode_manager_gpt"].return_value = episode_json

        await send_messages(TID, 3, mock_llm["session_manager_claude"])
        await update_single_user(TID)

        saved = await get_running_summary(TID)
        # Должен быть сжатый вариант (не 500 слов)
        assert len(saved.split()) < 400
