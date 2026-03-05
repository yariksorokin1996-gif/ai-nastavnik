"""
Тесты для bot/daily_messenger.py
10 тестов: generate_daily_message (3), send_daily_messages (4), check_silence (2),
           telegram_error_continues (1).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.prompts.memory_prompts import FALLBACK_DAILY_MESSAGES
from shared.llm_client import LLMError


# ---------------------------------------------------------------------------
# Хелперы и фикстуры
# ---------------------------------------------------------------------------

# "Сейчас" = 2026-03-04 13:00 UTC (16:00 MSK)
_FIXED_NOW_UTC = datetime(2026, 3, 4, 13, 0, 0, tzinfo=timezone.utc)
_FIXED_NOW_STR = "2026-03-04 13:00:00"


def _make_context():
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


# Активный пользователь, день 3 (создан ~2 дня назад)
_USER_ACTIVE = {
    "telegram_id": 123,
    "name": "Маша",
    "created_at": "2026-03-02 10:00:00",  # ~2 дня назад
    "last_message_at": "2026-03-04 10:00:00",  # 3ч назад
    "last_automated_msg_at": None,
    "current_phase": "ЗНАКОМСТВО",
    "messages_total": 10,
}

# Пользователь молчит 3+ дня (СТОП)
_USER_SILENT_3DAYS = {
    **_USER_ACTIVE,
    "last_message_at": "2026-03-01 10:00:00",  # 3 дня назад = 75ч
}

# Пользователь с недавним автоматическим сообщением (cooldown)
_USER_RECENT_AUTO = {
    **_USER_ACTIVE,
    "last_automated_msg_at": "2026-03-04 12:00:00",  # 1ч назад (< 2ч)
}

# Старый пользователь (день 13, после первой недели, молчание ~20ч < 48ч)
_USER_OLD = {
    **_USER_ACTIVE,
    "created_at": "2026-02-20 10:00:00",  # 12 дней назад
    "last_message_at": "2026-03-03 17:00:00",  # 20ч назад (< 48ч)
}

# Пользователь с 0 сообщений (только нажал /start)
_USER_ZERO_MSG = {
    **_USER_ACTIVE,
    "messages_total": 0,
}

# Пользователь для silence: last_message 25ч назад, нет автоматических
_USER_SILENCE_TRIGGER = {
    **_USER_ACTIVE,
    "last_message_at": "2026-03-03 12:00:00",  # 25ч назад
    "last_automated_msg_at": None,
}

# Пользователь для silence: cooldown 6ч (автоматическое 3ч назад)
_USER_SILENCE_COOLDOWN = {
    **_USER_ACTIVE,
    "last_message_at": "2026-03-03 12:00:00",  # 25ч назад
    "last_automated_msg_at": "2026-03-04 10:00:00",  # 3ч назад (< 6ч)
}


# ---------------------------------------------------------------------------
# 1. test_generate_daily_message_success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
async def test_generate_daily_message_success(mock_gpt, mock_pm, _mock_now):
    """call_gpt возвращает текст -> результат == текст, длина <= 500."""
    mock_gpt.return_value = "Привет, Маша! Как дела сегодня?"
    mock_pm.get_profile_as_text = AsyncMock(return_value="=== ПРОФИЛЬ ===\nИмя: Маша")
    mock_pm.get_profile = AsyncMock(return_value=None)

    from bot.daily_messenger import generate_daily_message

    result = await generate_daily_message(123, 3)

    assert result == "Привет, Маша! Как дела сегодня?"
    mock_gpt.assert_awaited_once()
    assert len(result) <= 500


# ---------------------------------------------------------------------------
# 2. test_generate_daily_message_uses_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
async def test_generate_daily_message_uses_profile(mock_gpt, mock_pm, _mock_now):
    """Текст профиля подставляется в промпт call_gpt."""
    profile_text = "=== ПРОФИЛЬ ===\nИмя: Маша\nГород: Москва"
    mock_pm.get_profile_as_text = AsyncMock(return_value=profile_text)
    mock_pm.get_profile = AsyncMock(return_value=None)
    mock_gpt.return_value = "Добрый день!"

    from bot.daily_messenger import generate_daily_message

    await generate_daily_message(123, 3)

    # Проверяем, что call_gpt вызван с промптом, содержащим профиль
    call_args = mock_gpt.call_args
    prompt_content = call_args[1]["messages"][0]["content"]
    assert profile_text in prompt_content


# ---------------------------------------------------------------------------
# 3. test_generate_daily_message_llm_error_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
async def test_generate_daily_message_llm_error_fallback(mock_gpt, mock_pm, _mock_now):
    """call_gpt raises LLMError -> возвращается FALLBACK."""
    mock_gpt.side_effect = LLMError("timeout")
    mock_pm.get_profile_as_text = AsyncMock(return_value="")
    mock_pm.get_profile = AsyncMock(return_value=None)

    from bot.daily_messenger import generate_daily_message

    result = await generate_daily_message(123, 3)

    assert result in FALLBACK_DAILY_MESSAGES


# ---------------------------------------------------------------------------
# 4. test_send_daily_first_week
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_send_daily_first_week(mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now):
    """Первая неделя: сообщение отправляется, create_daily_message и update_user вызваны."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_ACTIVE)])
    mock_db.has_daily_today = AsyncMock(return_value=False)
    mock_db.create_daily_message = AsyncMock()
    mock_db.add_message = AsyncMock()
    mock_db.update_user = AsyncMock()

    mock_gpt.return_value = "Привет, Маша!"
    mock_pm.get_profile_as_text = AsyncMock(return_value="Имя: Маша")
    mock_pm.get_profile = AsyncMock(return_value=None)

    ctx = _make_context()

    from bot.daily_messenger import send_daily_messages

    await send_daily_messages(ctx)

    ctx.bot.send_message.assert_awaited_once()
    mock_db.create_daily_message.assert_awaited_once()
    mock_db.update_user.assert_awaited_once()
    # Проверяем, что update_user вызван с last_automated_msg_at
    call_kwargs = mock_db.update_user.call_args[1]
    assert "last_automated_msg_at" in call_kwargs


# ---------------------------------------------------------------------------
# 5. test_send_daily_3days_silence_stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_send_daily_3days_silence_stop(
    mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now
):
    """Молчание 3+ дня -> сообщение НЕ отправляется."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_SILENT_3DAYS)])
    mock_db.has_daily_today = AsyncMock(return_value=False)

    ctx = _make_context()

    from bot.daily_messenger import send_daily_messages

    await send_daily_messages(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6. test_send_daily_cooldown_2h
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_send_daily_cooldown_2h(mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now):
    """Cooldown 2ч: автосообщение 1ч назад -> сообщение НЕ отправляется."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_RECENT_AUTO)])
    mock_db.has_daily_today = AsyncMock(return_value=False)

    ctx = _make_context()

    from bot.daily_messenger import send_daily_messages

    await send_daily_messages(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. test_send_daily_idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_send_daily_idempotency(mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now):
    """has_daily_today=True -> сообщение НЕ отправляется (идемпотентность)."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_ACTIVE)])
    mock_db.has_daily_today = AsyncMock(return_value=True)

    ctx = _make_context()

    from bot.daily_messenger import send_daily_messages

    await send_daily_messages(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. test_check_silence_triggers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_check_silence_triggers(mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now):
    """Молчание 25ч, нет автосообщения -> отправляем silence_reminder."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_SILENCE_TRIGGER)])
    mock_db.create_daily_message = AsyncMock()
    mock_db.add_message = AsyncMock()
    mock_db.update_user = AsyncMock()

    mock_gpt.return_value = "Привет, как ты?"
    mock_pm.get_profile_as_text = AsyncMock(return_value="Имя: Маша")
    mock_pm.get_profile = AsyncMock(return_value=None)

    ctx = _make_context()

    from bot.daily_messenger import check_silence

    await check_silence(ctx)

    ctx.bot.send_message.assert_awaited_once()
    # Проверяем, что add_message вызван с source="silence_reminder"
    mock_db.add_message.assert_awaited_once()
    call_args = mock_db.add_message.call_args
    assert call_args[0][2] == "Привет, как ты?"  # content
    assert call_args[1].get("source") == "silence_reminder" or call_args[0][3] == "silence_reminder"


# ---------------------------------------------------------------------------
# 9. test_check_silence_cooldown_6h
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_check_silence_cooldown_6h(
    mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now
):
    """Молчание 25ч, но автосообщение 3ч назад (< 6ч) -> НЕ отправляем."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_SILENCE_COOLDOWN)])

    ctx = _make_context()

    from bot.daily_messenger import check_silence

    await check_silence(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 10. test_send_daily_telegram_error_continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_send_daily_telegram_error_continues(
    mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now
):
    """Telegram-ошибка при отправке первому пользователю -> второму всё равно отправляем."""
    user1 = {**_USER_ACTIVE, "telegram_id": 111}
    user2 = {**_USER_ACTIVE, "telegram_id": 222}
    mock_db.get_all_users = AsyncMock(return_value=[user1, user2])
    mock_db.has_daily_today = AsyncMock(return_value=False)
    mock_db.create_daily_message = AsyncMock()
    mock_db.add_message = AsyncMock()
    mock_db.update_user = AsyncMock()

    mock_gpt.return_value = "Привет!"
    mock_pm.get_profile_as_text = AsyncMock(return_value="Имя: Маша")
    mock_pm.get_profile = AsyncMock(return_value=None)

    ctx = _make_context()
    # Первый вызов send_message -> ошибка, второй -> ОК
    ctx.bot.send_message.side_effect = [Exception("Telegram API error"), None]

    from bot.daily_messenger import send_daily_messages

    await send_daily_messages(ctx)

    # send_message вызван дважды (не упал после первой ошибки)
    assert ctx.bot.send_message.await_count == 2


# ---------------------------------------------------------------------------
# 11. test_send_daily_after_7_days_silence_lt_48h (Guard 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_send_daily_after_7_days_silence_lt_48h(
    mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now
):
    """После 7 дней, молчание < 48ч -> сообщение НЕ отправляется."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_OLD)])
    mock_db.has_daily_today = AsyncMock(return_value=False)

    ctx = _make_context()

    from bot.daily_messenger import send_daily_messages

    await send_daily_messages(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 12. test_check_silence_zero_messages (Guard 0)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now", return_value=_FIXED_NOW_STR)
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
@patch("bot.daily_messenger.database")
async def test_check_silence_zero_messages(
    mock_db, mock_gpt, mock_pm, _mock_now_utc, _mock_now
):
    """messages_total == 0 -> check_silence НЕ отправляет."""
    mock_db.get_all_users = AsyncMock(return_value=[dict(_USER_ZERO_MSG)])

    ctx = _make_context()

    from bot.daily_messenger import check_silence

    await check_silence(ctx)

    ctx.bot.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# 13. test_generate_daily_message_truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("bot.daily_messenger._now_utc", return_value=_FIXED_NOW_UTC)
@patch("bot.daily_messenger.profile_manager")
@patch("bot.daily_messenger.call_gpt", new_callable=AsyncMock)
async def test_generate_daily_message_truncation(mock_gpt, mock_pm, _mock_now):
    """GPT вернул > 500 символов -> обрезается до <= 500."""
    long_text = "Слово " * 120  # ~720 символов
    mock_gpt.return_value = long_text
    mock_pm.get_profile_as_text = AsyncMock(return_value="Имя: Маша")
    mock_pm.get_profile = AsyncMock(return_value=None)

    from bot.daily_messenger import generate_daily_message

    result = await generate_daily_message(123, 3)

    assert len(result) <= 500
    assert len(result) > 250  # не слишком короткий
