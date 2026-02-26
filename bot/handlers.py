from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from bot.session_manager import process_message
from bot.memory.database import get_user, get_patterns, update_user
from bot.transcriber import transcribe_voice
from shared.config import WEBAPP_URL

DISCLAIMER = (
    "⚠️ *Важно:* Этот бот — инструмент коучинга, не психотерапия. "
    "При серьёзных психологических проблемах обратись к специалисту."
)

START_MESSAGE = """Привет. Я — AI-наставник.

Помогаю разобраться с тем, что реально мешает — в деньгах, отношениях, жизни в целом.

Прежде чем начать — выбери, как ты хочешь работать:

{}""".format(DISCLAIMER)

STYLE_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton(
        "🌿 Мягко — с поддержкой и теплом",
        callback_data="style_1"
    )],
    [InlineKeyboardButton(
        "⚖️ Сбалансировано — честно, но без давления",
        callback_data="style_2"
    )],
    [InlineKeyboardButton(
        "🔥 Жёстко — прямо, без сантиментов",
        callback_data="style_3"
    )],
])

MODE_KEYBOARD = ReplyKeyboardMarkup(
    [["💬 Просто поболтать"]],
    resize_keyboard=True,
)

MODE_KEYBOARD_SUPPORT = ReplyKeyboardMarkup(
    [["🎯 Вернуться к работе"]],
    resize_keyboard=True,
)


def _webapp_keyboard():
    """Inline-клавиатура с кнопкой открытия Mini App (если WEBAPP_URL задан)."""
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✨ Открыть приложение",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )],
    ])

STYLE_NAMES = {
    1: "Мягкий",
    2: "Сбалансированный",
    3: "Жёсткий",
}

HELP_MESSAGE = """*Команды:*
/start — начать заново или сменить стиль
/app — открыть приложение
/status — твой текущий прогресс
/style — сменить стиль работы
/patterns — паттерны, которые я заметил
/reset — начать с чистого листа
/help — эта справка

*Важно:*
• Отвечай честно — я замечаю уклонения
• Каждый разговор заканчивается конкретным действием
• Утром спрошу что планируешь, вечером — сделала ли"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        START_MESSAGE,
        parse_mode="Markdown",
        reply_markup=STYLE_KEYBOARD,
    )


async def style_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    style_num = int(query.data.split("_")[1])
    telegram_id = query.from_user.id
    user_name = query.from_user.first_name or "друг"

    user = await get_user(telegram_id)
    if not user:
        from bot.memory.database import create_user
        user = await create_user(telegram_id, user_name)

    await update_user(telegram_id, coaching_style=style_num)

    style_name = STYLE_NAMES[style_num]
    style_descriptions = {
        1: "Буду поддерживать, задавать мягкие вопросы и помогать тебе найти ответы самой.",
        2: "Буду честным и прямым, но без давления. Поддержка и вызов в равных долях.",
        3: "Буду говорить прямо, называть вещи своими именами и не принимать отговорки.",
    }

    await query.edit_message_text(
        f"Выбран стиль: *{style_name}*\n\n"
        f"{style_descriptions[style_num]}\n\n"
        f"Стиль можно сменить в любой момент командой /style",
        parse_mode="Markdown",
    )

    await context.bot.send_message(
        chat_id=telegram_id,
        text="Напиши мне о том, с чем хочешь разобраться.",
        reply_markup=MODE_KEYBOARD,
    )

    # Показываем кнопку Mini App, если настроен
    webapp_kb = _webapp_keyboard()
    if webapp_kb:
        await context.bot.send_message(
            chat_id=telegram_id,
            text="Или открой приложение — там прогресс, цели и астро-карта дня:",
            reply_markup=webapp_kb,
        )


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


async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери стиль работы:",
        reply_markup=STYLE_KEYBOARD,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user = await get_user(telegram_id)
    if not user:
        await update.message.reply_text("Напиши /start чтобы начать.")
        return

    phase_labels = {
        "onboarding": "Знакомство",
        "diagnosis": "Диагностика",
        "goal": "Постановка цели",
        "planning": "Составление плана",
        "daily": "Ежедневная работа",
    }
    style_name = STYLE_NAMES.get(user.get("coaching_style", 2), "Сбалансированный")
    text = (
        f"*Твой прогресс:*\n\n"
        f"Фаза: {phase_labels.get(user['phase'], user['phase'])}\n"
        f"Цель: {user['goal'] or 'не поставлена'}\n"
        f"Дедлайн: {user['goal_deadline'] or 'не установлен'}\n"
        f"Сессий: {user['sessions_count']}\n"
        f"Стиль: {style_name}\n"
        f"Тариф: {'Про' if user['is_premium'] else 'Пробный'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def patterns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    patterns = await get_patterns(telegram_id)
    if not patterns:
        await update.message.reply_text("Паттерны ещё не выявлены. Продолжай работать.")
        return

    lines = ["*Паттерны, которые я заметил:*\n"]
    for p in patterns[:5]:
        lines.append(f"• {p['pattern_text']} — встречалось {p['count']} раз")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user = await get_user(telegram_id)
    if not user:
        await update.message.reply_text("Напиши /start чтобы начать.")
        return
    await update_user(telegram_id, phase="onboarding", sessions_count=0)
    await update.message.reply_text(
        "Начинаем с чистого листа. Расскажи, с чем хочешь разобраться."
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"

    await context.bot.send_chat_action(chat_id=telegram_id, action="typing")

    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()
        user_text = await transcribe_voice(bytes(voice_bytes))
    except Exception:
        await update.message.reply_text(
            "Не смогла распознать голосовое. Попробуй ещё раз или напиши текстом."
        )
        return

    try:
        response = await process_message(telegram_id, user_name, user_text)
    except Exception:
        await update.message.reply_text(
            "Произошла ошибка, попробуй ещё раз через минуту."
        )
        return

    await update.message.reply_text(
        f"🎤 _{user_text}_\n\n{response}",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    user_text = update.message.text

    if not user_text or not user_text.strip():
        await update.message.reply_text("Напиши что-нибудь — я здесь.")
        return

    if user_text == "💬 Просто поболтать":
        await update_user(telegram_id, mode="support")
        await update.message.reply_text(
            "Переключила в режим поддержки. Расскажи, что у тебя на душе.",
            reply_markup=MODE_KEYBOARD_SUPPORT,
        )
        return

    if user_text == "🎯 Вернуться к работе":
        await update_user(telegram_id, mode="coaching")
        await update.message.reply_text(
            "Возвращаемся к работе. На чём остановились?",
            reply_markup=MODE_KEYBOARD,
        )
        return

    await context.bot.send_chat_action(chat_id=telegram_id, action="typing")

    try:
        response = await process_message(telegram_id, user_name, user_text)
    except Exception:
        await update.message.reply_text(
            "Произошла ошибка, попробуй ещё раз через минуту."
        )
        return

    await update.message.reply_text(response)
