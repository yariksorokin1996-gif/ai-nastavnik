"""E2E тест контекста с паузой: E2E-5.

E2E-5: Сообщение → пауза 2ч → второе сообщение → system_prompt содержит 'Пауза 2 ч.'
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from bot.memory.database import update_user
from bot.session_manager import process_message
from tests.e2e.conftest import E2E_TELEGRAM_ID, time_ago


# ===========================================================================
# E2E-5: Контекст с паузой
# ===========================================================================


class TestE2E5PauseContext:
    """После паузы 2ч system_prompt для Claude содержит контекст паузы."""

    @pytest.mark.asyncio
    async def test_pause_in_system_prompt(self, e2e_user, mock_llm):
        """E2E-5: пауза 2ч → 'Пауза 2 ч.' в system kwarg call_claude."""

        # Отправить первое сообщение (создаёт last_message_at)
        resp1 = await process_message(E2E_TELEGRAM_ID, 1, "Привет", "Маша")
        assert resp1 is not None

        # Инжектируем паузу: last_message_at = 2 часа назад
        await update_user(E2E_TELEGRAM_ID, last_message_at=time_ago(125))

        # Сбрасываем mock чтобы отследить следующий вызов
        mock_llm["session_manager_claude"].reset_mock()

        # Захватываем system kwarg через side_effect
        captured_system = {}

        async def capture_claude(**kwargs):
            captured_system["system"] = kwargs.get("system", "")
            return "Рада, что ты вернулась! Как ты сейчас?"

        mock_llm["session_manager_claude"].side_effect = capture_claude

        # Отправить второе сообщение (после паузы)
        resp2 = await process_message(E2E_TELEGRAM_ID, 2, "Я вернулась", "Маша")
        assert resp2 is not None

        # Проверяем что call_claude был вызван
        # Если side_effect сработал, system должен быть захвачен
        # Если нет (call_claude вызван с positional args), проверяем call_args
        if captured_system.get("system"):
            system = captured_system["system"]
        else:
            # Fallback: проверяем call_args
            call_args = mock_llm["session_manager_claude"].call_args
            system = call_args.kwargs.get("system", "")

        assert "Пауза" in system
        assert "2 ч" in system
