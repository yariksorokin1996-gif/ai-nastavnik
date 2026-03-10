from __future__ import annotations

import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from bot.memory import database
from bot.memory.database import (
    get_user,
    get_patterns,
    delete_user_data,
    delete_user_completely,
    update_feeling,
    update_enactment,
)
from bot.session_manager import process_message
from bot.transcriber import transcribe_voice
from shared.config import WEBAPP_URL

logger = logging.getLogger(__name__)

MODE_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🎯 Идём к цели"), KeyboardButton("💬 По душам")]],
    resize_keyboard=True,
    one_time_keyboard=False,
)

START_MESSAGE = (
    "Привет 💛 Я Ева.\n\n"
    "Я не коуч, не терапевт — скорее подруга, "
    "которая умеет слушать и запоминать.\n\n"
    "Расскажи, что у тебя сейчас происходит?\n\n"
    "ᵉᵛᵃ — не замена специалисту. "
    "Если тебе нужна срочная помощь: 8-800-2000-122"
)

HELP_MESSAGE = (
    "Команды:\n"
    "/start — начать сначала\n"
    "/app — открыть приложение\n"
    "/status — твой прогресс\n"
    "/patterns — паттерны, которые я заметила\n"
    "/forget — забыть всё обо мне (сообщения останутся)\n"
    "/delete_account — удалить ВСЁ\n"
    "/help — эта справка"
)


def _webapp_keyboard():
    """Inline-клавиатура с кнопкой открытия Mini App (если WEBAPP_URL задан)."""
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "Личный кабинет",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — тёплое приветствие + закреплённое сообщение с WebApp."""
    await update.message.reply_text(START_MESSAGE, reply_markup=MODE_KEYBOARD)

    # Закрепляем сообщение с кнопкой WebApp вверху чата
    webapp_kb = _webapp_keyboard()
    if webapp_kb:
        try:
            pinned_msg = await update.message.reply_text(
                "Твой личный кабинет тут",
                reply_markup=webapp_kb,
            )
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=pinned_msg.message_id,
                disable_notification=True,
            )
        except Exception:
            logger.warning("Failed to pin webapp message", exc_info=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help — справка по командам."""
    await update.message.reply_text(HELP_MESSAGE)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status — прогресс пользователя."""
    telegram_id = update.effective_user.id
    user = await get_user(telegram_id)
    if not user:
        await update.message.reply_text("Напиши /start чтобы начать.")
        return

    phase = user.get("current_phase", "ЗНАКОМСТВО")
    messages_total = user.get("messages_total", 0)
    text = (
        f"Твой прогресс:\n\n"
        f"Фаза: {phase}\n"
        f"Сообщений: {messages_total}"
    )
    await update.message.reply_text(text)


async def patterns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /patterns — паттерны, замеченные Евой."""
    telegram_id = update.effective_user.id
    patterns = await get_patterns(telegram_id)
    if not patterns:
        await update.message.reply_text("Паттерны ещё не выявлены. Продолжай работать.")
        return

    lines = ["*Паттерны, которые я заметила:*\n"]
    for p in patterns[:5]:
        lines.append(f"• {p['pattern_text']} — встречалось {p['count']} раз")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /app — открывает Mini App."""
    webapp_kb = _webapp_keyboard()
    if webapp_kb:
        await update.message.reply_text(
            "Открой приложение:",
            reply_markup=webapp_kb,
        )
    else:
        await update.message.reply_text(
            "Mini App пока не доступен."
        )


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /forget — забыть всё о пользователе (2-шаговое подтверждение)."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да, забудь", callback_data="forget_confirm"),
            InlineKeyboardButton("Нет, оставь", callback_data="forget_cancel"),
        ],
    ])
    await update.message.reply_text(
        "Удалить всё что я запомнила о тебе? Сообщения останутся.",
        reply_markup=keyboard,
    )


async def delete_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /delete_account — удалить ВСЁ (2-шаговое подтверждение)."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да, удалить аккаунт", callback_data="delete_confirm"),
            InlineKeyboardButton("Нет", callback_data="delete_cancel"),
        ],
    ])
    await update.message.reply_text(
        "Удалить ВСЁ — и сообщения, и данные? Это необратимо.",
        reply_markup=keyboard,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    telegram_id = update.effective_user.id
    user_name = update.effective_user.first_name or None
    user_text = update.message.text
    message_id = update.message.message_id

    if not user_text or not user_text.strip():
        return

    # Перехват кнопок режимов
    if user_text in ("🎯 Идём к цели", "💬 По душам"):
        mode = "goal" if "цели" in user_text else "soul"
        await database.update_user(telegram_id, conversation_mode=mode)
        ack = "Окей, фокус на цели 🎯" if mode == "goal" else "Окей, просто поболтаем 💬"
        await update.message.reply_text(ack, reply_markup=MODE_KEYBOARD)
        return

    await context.bot.send_chat_action(chat_id=telegram_id, action=ChatAction.TYPING)

    response = await process_message(
        telegram_id=telegram_id,
        message_id=message_id,
        text=user_text,
        user_name=user_name,
    )

    if response is not None:
        await update.message.reply_text(response, reply_markup=MODE_KEYBOARD)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений."""
    telegram_id = update.effective_user.id
    user_name = update.effective_user.first_name or None
    message_id = update.message.message_id

    # Проверка длительности: > 3 минут → мягкий отказ
    duration = update.message.voice.duration or 0
    if duration > 180:
        await update.message.reply_text(
            "Ой, это длинное сообщение 🙈 "
            "Можешь записать покороче — до 3 минут? Или написать текстом."
        )
        return

    await context.bot.send_chat_action(chat_id=telegram_id, action=ChatAction.TYPING)

    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()
        user_text = await transcribe_voice(bytes(voice_bytes))
    except Exception:
        await update.message.reply_text("Прости, не расслышала. Напиши текстом? 🙏")
        return

    response = await process_message(
        telegram_id=telegram_id,
        message_id=message_id,
        text=user_text,
        user_name=user_name,
        is_voice=True,
    )

    if response is not None:
        await update.message.reply_text(response, reply_markup=MODE_KEYBOARD)


async def handle_other_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фото, стикеров, документов и прочего."""
    await update.message.reply_text(
        "Прости, я пока умею только читать текст и слушать голосовые 🙂 Напиши мне словами?"
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline-кнопок."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "forget_confirm":
        telegram_id = query.from_user.id
        await delete_user_data(telegram_id)
        await query.edit_message_text("Готово, я всё забыла. Начинаем с чистого листа 💛")

    elif data == "forget_cancel":
        await query.edit_message_text("Хорошо, оставляю всё как есть.")

    elif data == "delete_confirm":
        telegram_id = query.from_user.id
        await delete_user_completely(telegram_id)
        await query.edit_message_text("Все данные удалены. Если захочешь вернуться — /start")

    elif data == "delete_cancel":
        await query.edit_message_text("Хорошо, ничего не удаляю.")

    elif data.startswith("feeling:"):
        parts = data.split(":")
        if len(parts) == 3:
            try:
                feedback_id = int(parts[1])
                value = int(parts[2])
            except (ValueError, IndexError):
                logger.warning("Invalid feeling callback data: %s", data)
                return
            await update_feeling(feedback_id, value)
            responses = {
                1: "Рада это слышать 💛",
                2: "Понимаю, я рядом 🤍",
                3: "Мне жаль. Если захочешь поговорить — я здесь 💙",
            }
            await query.edit_message_text(responses.get(value, "Спасибо 💛"))

    elif data.startswith("enact:"):
        parts = data.split(":")
        if len(parts) == 3:
            try:
                feedback_id = int(parts[1])
                value = int(parts[2])
            except (ValueError, IndexError):
                logger.warning("Invalid enact callback data: %s", data)
                return
            await update_enactment(feedback_id, value)
            responses = {
                1: "Круто! 🎉",
                0: "Ничего, попробуешь когда будешь готова 💛",
            }
            await query.edit_message_text(responses.get(value, "Записала! 💛"))
