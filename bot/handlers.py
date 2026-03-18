from __future__ import annotations

import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
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
    is_user_allowed,
    add_allowed_user,
    remove_allowed_user,
    get_allowed_users,
)
from bot.session_manager import process_message
from bot.transcriber import transcribe_voice
from shared.config import OWNER_TELEGRAM_ID

logger = logging.getLogger(__name__)

CLOSED_MESSAGE = "Привет! Ева сейчас работает в закрытом тестировании 💛"


async def _check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет whitelist. Если юзер не допущен — уведомляет owner. Возвращает True если доступ есть."""
    telegram_id = update.effective_user.id
    if await is_user_allowed(telegram_id):
        return True
    user_name = update.effective_user.first_name or "?"
    logger.info("Blocked user: %s (name=%s)", telegram_id, user_name)
    await update.message.reply_text(CLOSED_MESSAGE)
    try:
        await context.bot.send_message(
            OWNER_TELEGRAM_ID,
            f"Новый юзер хочет доступ:\nID: {telegram_id}\nИмя: {user_name}\n\n/allow {telegram_id}",
        )
    except Exception:
        logger.warning("Failed to notify owner about blocked user %s", telegram_id)
    return False

START_MESSAGE = (
    "Привет! Я Ева 💛\n\n"
    "Я не бот в обычном смысле — я подруга, которая слушает "
    "и помнит то, чем ты делишься. Не осуждаю, не лезу "
    "с советами, не исчезаю.\n\n"
    "Пиши текстом или голосовыми — как удобнее.\n\n"
    "У меня два режима:\n"
    "🎯 /goal — «Идём к цели» — помогу разобраться и подсвечу "
    "то, что ты сама можешь не замечать\n"
    "💬 /soul — «По душам» — просто поговорим, без анализа\n\n"
    "Расскажи, что у тебя сейчас происходит?"
)

HELP_MESSAGE = (
    "Команды:\n"
    "/goal — режим «Идём к цели»\n"
    "/soul — режим «По душам»\n"
    "/about — что умеет Ева"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — тёплое приветствие."""
    if not await _check_access(update, context):
        return
    await update.message.reply_text(
        START_MESSAGE, reply_markup=ReplyKeyboardRemove(),
    )


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


async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /goal — режим «Идём к цели»."""
    telegram_id = update.effective_user.id
    await database.update_user(telegram_id, conversation_mode="goal")
    await update.message.reply_text(
        "Окей, фокус на цели. Рассказывай, что хочешь изменить?",
    )


async def soul_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /soul — режим «По душам»."""
    telegram_id = update.effective_user.id
    await database.update_user(telegram_id, conversation_mode="soul")
    await update.message.reply_text(
        "Окей, просто поболтаем. Я тут, рассказывай.",
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about — что умеет Ева."""
    await update.message.reply_text(
        "Я Ева — подруга, которая слушает.\n\n"
        "Что я умею:\n"
        "— Слушать и помнить то, чем делишься\n"
        "— Замечать повторения и мягко говорить о них\n"
        "— Помогать увидеть ситуацию иначе — через вопросы, не советы\n"
        "— Быть рядом когда тяжело — без нравоучений\n\n"
        "Режимы:\n"
        "/goal — Идём к цели\n"
        "/soul — По душам",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    if not await _check_access(update, context):
        return
    telegram_id = update.effective_user.id
    user_name = update.effective_user.first_name or None
    user_text = update.message.text
    message_id = update.message.message_id

    if not user_text or not user_text.strip():
        return

    await context.bot.send_chat_action(chat_id=telegram_id, action=ChatAction.TYPING)

    response = await process_message(
        telegram_id=telegram_id,
        message_id=message_id,
        text=user_text,
        user_name=user_name,
    )

    if response is not None:
        await update.message.reply_text(response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений."""
    if not await _check_access(update, context):
        return
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
        await update.message.reply_text(response)


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


# ---------------------------------------------------------------------------
# Owner-only: whitelist management
# ---------------------------------------------------------------------------


async def allow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /allow ID — добавить юзера в whitelist (только owner)."""
    if update.effective_user.id != OWNER_TELEGRAM_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /allow 123456789")
        return
    try:
        tid = int(args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
        return
    await add_allowed_user(tid, added_by=update.effective_user.id)
    await update.message.reply_text(f"✅ Юзер {tid} добавлен")


async def deny_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /deny ID — убрать юзера из whitelist (только owner)."""
    if update.effective_user.id != OWNER_TELEGRAM_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /deny 123456789")
        return
    try:
        tid = int(args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
        return
    await remove_allowed_user(tid)
    await update.message.reply_text(f"❌ Юзер {tid} удалён")


async def allowed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /allowed — список допущенных юзеров (только owner)."""
    if update.effective_user.id != OWNER_TELEGRAM_ID:
        return
    users = await get_allowed_users()
    if not users:
        await update.message.reply_text("Список пуст")
        return
    text = "Допущенные юзеры:\n" + "\n".join(str(u) for u in users)
    await update.message.reply_text(text)
