"""Тесты конвейера обработки сообщений bot.session_manager."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from shared.models import CrisisResult, ContextMeta
from shared.safety import CRISIS_RESPONSE_LEVEL3, CRISIS_INSTRUCTION_LEVEL2


# ---------------------------------------------------------------------------
# Авто-очистка модульного состояния перед каждым тестом
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_state():
    """Reset module state before each test."""
    from bot import session_manager
    session_manager._user_locks.clear()
    session_manager._rate_counters.clear()
    session_manager._consecutive_errors.clear()
    yield
    session_manager._user_locks.clear()
    session_manager._rate_counters.clear()
    session_manager._consecutive_errors.clear()


# ---------------------------------------------------------------------------
# Стандартная фикстура с моками всех зависимостей
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_deps():
    """Standard mock setup for session_manager tests."""
    with (
        patch("bot.session_manager.is_message_processed", new_callable=AsyncMock, return_value=False) as mock_idempotency,
        patch("bot.session_manager.get_user", new_callable=AsyncMock, return_value={"messages_total": 5, "current_phase": "ЗНАКОМСТВО", "last_message_at": None}) as mock_get_user,
        patch("bot.session_manager.create_user", new_callable=AsyncMock, return_value={"messages_total": 0, "current_phase": "ЗНАКОМСТВО", "last_message_at": None}) as mock_create_user,
        patch("bot.session_manager.add_message", new_callable=AsyncMock) as mock_add_msg,
        patch("bot.session_manager.mark_message_processed", new_callable=AsyncMock) as mock_mark,
        patch("bot.session_manager.get_recent_messages", new_callable=AsyncMock, return_value=[]) as mock_recent,
        patch("bot.session_manager.update_user", new_callable=AsyncMock) as mock_update,
        patch("bot.session_manager.detect_crisis", new_callable=AsyncMock, return_value=CrisisResult(level=0, trigger=None, is_verified=True)) as mock_crisis,
        patch("bot.session_manager.call_claude", new_callable=AsyncMock, return_value="Привет! Рада тебя слышать.") as mock_claude,
        patch("bot.session_manager.build_context", new_callable=AsyncMock, return_value=("system prompt", 1500, ContextMeta())) as mock_context,
        patch("bot.session_manager.add_pending_fact", new_callable=AsyncMock) as mock_pending,
        patch("bot.session_manager.add_emotion", new_callable=AsyncMock) as mock_emotion,
        patch("bot.session_manager.evaluate_phase", new_callable=AsyncMock) as mock_eval_phase,
        patch("bot.session_manager.add_phase_transition", new_callable=AsyncMock) as mock_phase_transition,
    ):
        yield {
            "is_message_processed": mock_idempotency,
            "get_user": mock_get_user,
            "create_user": mock_create_user,
            "add_message": mock_add_msg,
            "mark_message_processed": mock_mark,
            "get_recent_messages": mock_recent,
            "update_user": mock_update,
            "detect_crisis": mock_crisis,
            "call_claude": mock_claude,
            "build_context": mock_context,
            "add_pending_fact": mock_pending,
            "add_emotion": mock_emotion,
            "evaluate_phase": mock_eval_phase,
            "add_phase_transition": mock_phase_transition,
        }


# ===========================================================================
# Core pipeline
# ===========================================================================


class TestCorePipeline:
    """Тесты основного конвейера process_message."""

    @pytest.mark.asyncio
    async def test_idempotency_returns_none(self, mock_deps: dict) -> None:
        """#1: is_message_processed=True → process_message возвращает None."""
        from bot.session_manager import process_message

        mock_deps["is_message_processed"].return_value = True

        result = await process_message(111, 999, "привет", "Маша")

        assert result is None
        mock_deps["call_claude"].assert_not_called()

    @pytest.mark.asyncio
    async def test_new_user_creates_user(self, mock_deps: dict) -> None:
        """#2: get_user=None → create_user вызывается с именем."""
        from bot.session_manager import process_message

        mock_deps["get_user"].return_value = None

        await process_message(111, 1, "привет", "Маша")

        mock_deps["create_user"].assert_called_once_with(111, name="Маша")

    @pytest.mark.asyncio
    async def test_existing_user_no_create(self, mock_deps: dict) -> None:
        """#3: get_user возвращает dict → create_user НЕ вызывается."""
        from bot.session_manager import process_message

        await process_message(111, 1, "привет", "Маша")

        mock_deps["create_user"].assert_not_called()

    @pytest.mark.asyncio
    async def test_crisis_level3_returns_crisis_response(self, mock_deps: dict) -> None:
        """#4: crisis level=3 → CRISIS_RESPONSE_LEVEL3, call_claude не вызван."""
        from bot.session_manager import process_message

        mock_deps["detect_crisis"].return_value = CrisisResult(
            level=3, trigger="хочу умереть", is_verified=True,
        )

        result = await process_message(111, 1, "хочу умереть", "Маша")

        assert result == CRISIS_RESPONSE_LEVEL3
        mock_deps["call_claude"].assert_not_called()

    @pytest.mark.asyncio
    async def test_crisis_level2_appends_instruction(self, mock_deps: dict) -> None:
        """#5: crisis level=2 → call_claude вызван, system_prompt содержит CRISIS_INSTRUCTION_LEVEL2."""
        from bot.session_manager import process_message

        mock_deps["detect_crisis"].return_value = CrisisResult(
            level=2, trigger="бьёт меня", is_verified=True,
        )

        await process_message(111, 1, "муж бьёт меня", "Маша")

        mock_deps["call_claude"].assert_called_once()
        call_kwargs = mock_deps["call_claude"].call_args
        system_arg = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system", "")
        assert CRISIS_INSTRUCTION_LEVEL2 in system_arg

    @pytest.mark.asyncio
    async def test_new_user_plus_crisis_level3(self, mock_deps: dict) -> None:
        """#6: get_user=None + crisis L3 → create_user И CRISIS_RESPONSE_LEVEL3."""
        from bot.session_manager import process_message

        mock_deps["get_user"].return_value = None
        mock_deps["detect_crisis"].return_value = CrisisResult(
            level=3, trigger="суицид", is_verified=True,
        )

        result = await process_message(111, 1, "суицид", "Маша")

        assert result == CRISIS_RESPONSE_LEVEL3
        mock_deps["create_user"].assert_called_once_with(111, name="Маша")


# ===========================================================================
# Rate limiting
# ===========================================================================


class TestRateLimiting:
    """Тесты rate limiting."""

    def test_rate_limit_blocks_after_max(self) -> None:
        """#7: после заполнения лимита _check_rate_limit → False."""
        from bot.session_manager import _check_rate_limit, _rate_counters
        from shared.config import RATE_LIMIT_PER_MINUTE

        tid = 111
        # Заполняем счётчик до лимита
        now = time.monotonic()
        _rate_counters[tid] = [now] * RATE_LIMIT_PER_MINUTE

        result = _check_rate_limit(tid)
        assert result is False

    def test_rate_limit_boundary_60_ok_61_blocked(self) -> None:
        """#8: 60 запросов проходят, 61-й блокируется."""
        from bot.session_manager import _check_rate_limit
        from shared.config import RATE_LIMIT_PER_MINUTE

        tid = 222

        # 60 вызовов должны пройти
        for i in range(RATE_LIMIT_PER_MINUTE):
            assert _check_rate_limit(tid) is True, f"Запрос {i+1} должен пройти"

        # 61-й блокируется
        assert _check_rate_limit(tid) is False

    def test_rate_limit_cleanup_old_timestamps(self) -> None:
        """#9: старые timestamps (>60 сек) очищаются."""
        from bot.session_manager import _check_rate_limit, _rate_counters
        from shared.config import RATE_LIMIT_PER_MINUTE

        tid = 333
        # Добавляем старые timestamps (>60 сек назад)
        old_time = time.monotonic() - 120  # 2 минуты назад
        _rate_counters[tid] = [old_time] * RATE_LIMIT_PER_MINUTE

        # Должно пройти — старые записи очищены
        result = _check_rate_limit(tid)
        assert result is True
        # После очистки и добавления нового — должен быть 1 элемент
        assert len(_rate_counters[tid]) == 1


# ===========================================================================
# Claude call
# ===========================================================================


class TestClaudeCall:
    """Тесты вызова Claude и обработки ошибок."""

    @pytest.mark.asyncio
    async def test_successful_response_saved(self, mock_deps: dict) -> None:
        """#10: call_claude возвращает текст → ответ сохраняется через add_message."""
        from bot.session_manager import process_message

        mock_deps["call_claude"].return_value = "Ответ от Евы"

        result = await process_message(111, 1, "привет", "Маша")

        assert result == "Ответ от Евы"
        # add_message вызывается дважды: user + assistant
        calls = mock_deps["add_message"].call_args_list
        # Ищем вызов с role="assistant"
        assistant_calls = [c for c in calls if c.args[1] == "assistant"]
        assert len(assistant_calls) == 1
        assert assistant_calls[0].args[2] == "Ответ от Евы"

    @pytest.mark.asyncio
    async def test_llm_error_returns_fallback(self, mock_deps: dict) -> None:
        """#11: call_claude бросает LLMError → fallback ответ."""
        from bot.session_manager import process_message
        from shared.llm_client import LLMError

        mock_deps["call_claude"].side_effect = LLMError("timeout")

        result = await process_message(111, 1, "привет", "Маша")

        assert result is not None
        # Первая ошибка → error_count=1 → idx=1 → _FALLBACK_VARIANTS[1]
        from bot.session_manager import _FALLBACK_VARIANTS
        assert result == _FALLBACK_VARIANTS[1]

    @pytest.mark.asyncio
    async def test_3_consecutive_errors_logs_alert(self, mock_deps: dict) -> None:
        """#12: 3 последовательных ошибки → logger.error с 'ALERT: consecutive_errors'."""
        from bot.session_manager import process_message, _consecutive_errors
        from shared.llm_client import LLMError

        mock_deps["call_claude"].side_effect = LLMError("timeout")
        # Выставляем 2 ошибки уже было
        _consecutive_errors[111] = 2

        with patch("bot.session_manager.logger") as mock_logger:
            await process_message(111, 1, "привет", "Маша")

            # Проверяем что logger.error вызван с ALERT: consecutive_errors
            alert_calls = [
                c for c in mock_logger.error.call_args_list
                if "ALERT: consecutive_errors" in str(c)
            ]
            assert len(alert_calls) >= 1

    @pytest.mark.asyncio
    async def test_errors_reset_on_success(self, mock_deps: dict) -> None:
        """#13: после ошибок успешный вызов сбрасывает счётчик."""
        from bot.session_manager import process_message, _consecutive_errors

        _consecutive_errors[111] = 5
        mock_deps["call_claude"].return_value = "Отлично!"

        await process_message(111, 1, "привет", "Маша")

        assert 111 not in _consecutive_errors


# ===========================================================================
# UX
# ===========================================================================


class TestUX:
    """Тесты UX-правил."""

    def test_fallback_persistent_after_3_errors(self) -> None:
        """#14: 3+ ошибок → _FALLBACK_PERSISTENT с текстом 'сломалось'."""
        from bot.session_manager import _get_fallback_response, _consecutive_errors, _FALLBACK_PERSISTENT

        _consecutive_errors[111] = 3

        result = _get_fallback_response(111)

        assert result == _FALLBACK_PERSISTENT
        assert "сломалось" in result

    def test_truncation_at_period(self) -> None:
        """#15: ответ > 4000 символов → обрезка до последней точки."""
        from bot.session_manager import _truncate_response

        # Создаём текст >4000 символов с точками внутри
        long_text = "Привет. " * 600  # ~4800 символов
        result = _truncate_response(long_text, max_len=4000)

        assert len(result) <= 4000
        assert result.endswith(".")

    def test_truncation_short_text_unchanged(self) -> None:
        """Короткий текст не обрезается."""
        from bot.session_manager import _truncate_response

        short_text = "Коротко."
        result = _truncate_response(short_text, max_len=4000)
        assert result == short_text

    @pytest.mark.asyncio
    async def test_rate_limit_warm_message(self, mock_deps: dict) -> None:
        """#16: rate limit → ответ содержит 'быстро пишешь'."""
        from bot.session_manager import process_message, _rate_counters
        from shared.config import RATE_LIMIT_PER_MINUTE

        # Заполняем rate limit
        now = time.monotonic()
        _rate_counters[111] = [now] * RATE_LIMIT_PER_MINUTE

        result = await process_message(111, 1, "привет", "Маша")

        assert result is not None
        assert "быстро пишешь" in result

    @pytest.mark.asyncio
    async def test_post_crisis_context_in_system_prompt(self, mock_deps: dict) -> None:
        """#17: последний assistant msg = CRISIS_RESPONSE_LEVEL3 → system_prompt содержит пост-кризисный текст."""
        from bot.session_manager import process_message

        # Подставляем recent messages с кризисным ответом
        mock_deps["get_recent_messages"].return_value = [
            {"role": "user", "content": "мне плохо"},
            {"role": "assistant", "content": CRISIS_RESPONSE_LEVEL3},
            {"role": "user", "content": "мне лучше"},
        ]

        await process_message(111, 1, "мне лучше", "Маша")

        mock_deps["call_claude"].assert_called_once()
        call_kwargs = mock_deps["call_claude"].call_args
        system_arg = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system", "")
        assert "кризисном" in system_arg


# ===========================================================================
# Background tasks
# ===========================================================================


class TestBackgroundTasks:
    """Тесты фоновых задач: phase check и mini-update."""

    @pytest.mark.asyncio
    async def test_phase_check_triggers_on_10th_message(self, mock_deps: dict) -> None:
        """#18: messages_total=9 (станет 10) → create_task вызывается для _check_phase_transition."""
        from bot.session_manager import process_message

        mock_deps["get_user"].return_value = {
            "messages_total": 9,
            "current_phase": "ЗНАКОМСТВО",
            "last_message_at": None,
        }

        with patch("bot.session_manager.asyncio.create_task") as mock_create_task:
            await process_message(111, 1, "привет", "Маша")

            # Должно быть минимум 2 create_task: mini_memory_update + phase_check
            assert mock_create_task.call_count >= 2

    @pytest.mark.asyncio
    async def test_phase_check_not_on_11th_message(self, mock_deps: dict) -> None:
        """#19: messages_total=10 (станет 11) → phase check НЕ вызывается."""
        from bot.session_manager import process_message

        mock_deps["get_user"].return_value = {
            "messages_total": 10,
            "current_phase": "ЗНАКОМСТВО",
            "last_message_at": None,
        }

        with patch("bot.session_manager.asyncio.create_task") as mock_create_task:
            await process_message(111, 1, "привет", "Маша")

            # Должен быть только 1 create_task — для mini_memory_update
            assert mock_create_task.call_count == 1


# ===========================================================================
# Mini memory update
# ===========================================================================


class TestMiniMemoryUpdate:
    """Тесты мини-обновления памяти (_mini_memory_update)."""

    @pytest.mark.asyncio
    async def test_extracts_name(self, mock_deps: dict) -> None:
        """#20: 'моя Настя' → add_pending_fact с person, Настя."""
        from bot.session_manager import _mini_memory_update

        await _mini_memory_update(111, "моя Настя очень красивая", "Ответ")

        mock_deps["add_pending_fact"].assert_any_call(
            111, "person", "Настя", confidence="medium",
        )

    @pytest.mark.asyncio
    async def test_stop_list_blocks_name(self, mock_deps: dict) -> None:
        """#21: 'мой Бог' → add_pending_fact НЕ вызывается (стоп-лист)."""
        from bot.session_manager import _mini_memory_update

        await _mini_memory_update(111, "мой Бог какой день!", "Ответ")

        # add_pending_fact не должен быть вызван с "person", "Бог"
        for call in mock_deps["add_pending_fact"].call_args_list:
            if len(call.args) >= 3:
                assert not (call.args[1] == "person" and call.args[2] == "Бог")

    @pytest.mark.asyncio
    async def test_extracts_age(self, mock_deps: dict) -> None:
        """#22: 'мне 32 года' → add_pending_fact с age, '32'."""
        from bot.session_manager import _mini_memory_update

        await _mini_memory_update(111, "мне 32 года и я устала", "Ответ")

        mock_deps["add_pending_fact"].assert_any_call(
            111, "age", "32", confidence="high",
        )

    @pytest.mark.asyncio
    async def test_extracts_emotion(self, mock_deps: dict) -> None:
        """#23: 'бесит' → add_emotion с 'злость'."""
        from bot.session_manager import _mini_memory_update

        await _mini_memory_update(111, "меня всё бесит", "Ответ")

        mock_deps["add_emotion"].assert_any_call(111, "злость")
