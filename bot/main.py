import asyncio
import logging
from telegram import MenuButtonWebApp, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from bot.handlers import (
    start, help_command, status_command, patterns_command,
    style_command, style_choice, reset_command, handle_voice, handle_message,
    app_command,
)
from bot.scheduler import setup_scheduler
from bot.memory.database import init_db
from shared.config import TELEGRAM_BOT_TOKEN, WEBAPP_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application):
    await init_db()
    logger.info("База данных инициализирована")

    # Устанавливаем Menu Button с Mini App если WEBAPP_URL задан
    if WEBAPP_URL:
        try:
            await app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Приложение",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            )
            logger.info("Menu Button с Mini App установлен")
        except Exception as e:
            logger.warning(f"Не удалось установить Menu Button: {e}")


async def error_handler(update, context):
    logger.error(f"Exception: {context.error}", exc_info=context.error)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("patterns", patterns_command))
    app.add_handler(CommandHandler("style", style_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("app", app_command))

    # Выбор стиля через inline кнопки
    app.add_handler(CallbackQueryHandler(style_choice, pattern="^style_"))

    # Голосовые сообщения
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Все текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Глобальный обработчик ошибок
    app.add_error_handler(error_handler)

    # Планировщик чек-инов
    setup_scheduler(app)

    logger.info("AI Наставник запущен")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
