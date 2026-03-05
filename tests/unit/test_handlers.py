"""Тесты для bot.handlers — команды, коллбеки, обработка сообщений."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import (
    start,
    help_command,
    status_command,
    forget_command,
    handle_voice,
    handle_other_media,
    callback_handler,
)


# ---------------------------------------------------------------------------
# Фабрики моков
# ---------------------------------------------------------------------------

def make_update(text=None, message_id=123, user_id=111, first_name="Маша"):
    """Мок объекта Update с сообщением."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = first_name

    message = MagicMock()
    message.text = text
    message.message_id = message_id
    message.reply_text = AsyncMock()
    update.message = message

    return update


def make_callback_update(data, user_id=111):
    """Мок объекта Update с callback_query."""
    update = MagicMock()
    query = MagicMock()
    query.data = data
    query.from_user.id = user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query
    update.message = None
    return update


def make_context():
    """Мок объекта context."""
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.get_file = AsyncMock()
    return context


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_contains_eva() -> None:
    """Команда /start — ответ содержит 'Ева'."""
    update = make_update()
    context = make_context()

    await start(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Ева" in text


@pytest.mark.asyncio
async def test_start_contains_disclaimer() -> None:
    """Команда /start — ответ содержит телефон горячей линии."""
    update = make_update()
    context = make_context()

    await start(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "8-800-2000-122" in text


@pytest.mark.asyncio
async def test_help_contains_commands() -> None:
    """Команда /help — ответ содержит /forget и /delete_account."""
    update = make_update()
    context = make_context()

    await help_command(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "/forget" in text
    assert "/delete_account" in text


@pytest.mark.asyncio
@patch("bot.handlers.get_user", new_callable=AsyncMock, return_value=None)
async def test_status_new_user(mock_get_user: AsyncMock) -> None:
    """Команда /status — новый пользователь -> 'напиши /start'."""
    update = make_update(user_id=999)
    context = make_context()

    await status_command(update, context)

    mock_get_user.assert_called_once_with(999)
    text = update.message.reply_text.call_args[0][0]
    assert "/start" in text


@pytest.mark.asyncio
@patch("bot.handlers.get_user", new_callable=AsyncMock)
async def test_status_existing_user(mock_get_user: AsyncMock) -> None:
    """Команда /status — существующий пользователь -> фаза и кол-во сообщений."""
    mock_get_user.return_value = {
        "current_phase": "ЗЕРКАЛО",
        "messages_total": 42,
    }
    update = make_update(user_id=111)
    context = make_context()

    await status_command(update, context)

    text = update.message.reply_text.call_args[0][0]
    assert "ЗЕРКАЛО" in text
    assert "42" in text


# ---------------------------------------------------------------------------
# Коллбеки
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forget_command_shows_keyboard() -> None:
    """Команда /forget — показывает inline-клавиатуру с 'forget_confirm'."""
    update = make_update()
    context = make_context()

    await forget_command(update, context)

    update.message.reply_text.assert_called_once()
    kwargs = update.message.reply_text.call_args
    reply_markup = kwargs[1]["reply_markup"] if "reply_markup" in kwargs[1] else kwargs.kwargs["reply_markup"]
    # Проверяем, что в клавиатуре есть кнопка с callback_data="forget_confirm"
    buttons_data = [
        btn.callback_data
        for row in reply_markup.inline_keyboard
        for btn in row
    ]
    assert "forget_confirm" in buttons_data


@pytest.mark.asyncio
@patch("bot.handlers.delete_user_data", new_callable=AsyncMock)
async def test_forget_confirm_calls_delete(mock_delete: AsyncMock) -> None:
    """Коллбек forget_confirm — вызывает delete_user_data."""
    update = make_callback_update(data="forget_confirm", user_id=111)
    context = make_context()

    await callback_handler(update, context)

    mock_delete.assert_called_once_with(111)
    update.callback_query.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.delete_user_completely", new_callable=AsyncMock)
async def test_delete_confirm_calls_delete_completely(mock_delete: AsyncMock) -> None:
    """Коллбек delete_confirm — вызывает delete_user_completely."""
    update = make_callback_update(data="delete_confirm", user_id=222)
    context = make_context()

    await callback_handler(update, context)

    mock_delete.assert_called_once_with(222)
    update.callback_query.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.update_feeling", new_callable=AsyncMock)
async def test_feeling_callback(mock_feeling: AsyncMock) -> None:
    """Коллбек feeling:42:2 — вызывает update_feeling(42, 2)."""
    update = make_callback_update(data="feeling:42:2")
    context = make_context()

    await callback_handler(update, context)

    mock_feeling.assert_called_once_with(42, 2)
    update.callback_query.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.update_enactment", new_callable=AsyncMock)
async def test_enact_callback(mock_enact: AsyncMock) -> None:
    """Коллбек enact:42:1 — вызывает update_enactment(42, 1)."""
    update = make_callback_update(data="enact:42:1")
    context = make_context()

    await callback_handler(update, context)

    mock_enact.assert_called_once_with(42, 1)
    update.callback_query.answer.assert_called_once()


# ---------------------------------------------------------------------------
# Обработка сообщений / медиа
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_other_media_text_only() -> None:
    """handle_other_media — ответ содержит слово 'текст'."""
    update = make_update()
    context = make_context()

    await handle_other_media(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "текст" in text


@pytest.mark.asyncio
@patch("bot.handlers.transcribe_voice", new_callable=AsyncMock)
async def test_handle_voice_transcription_fails(mock_transcribe: AsyncMock) -> None:
    """handle_voice — ошибка транскрипции -> 'не расслышала'."""
    update = make_update(user_id=111)
    # Настраиваем voice-атрибут
    update.message.voice = MagicMock()
    update.message.voice.file_id = "test_file_id"
    update.message.voice.duration = 30  # 30 секунд — в пределах лимита

    context = make_context()
    # get_file выбрасывает ошибку -> попадаем в except
    context.bot.get_file.side_effect = Exception("file download failed")

    await handle_voice(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "не расслышала" in text
