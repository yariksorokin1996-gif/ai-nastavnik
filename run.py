"""
Единый entry point: запускает Telegram-бота и FastAPI-сервер параллельно.
"""
import asyncio
import logging
import os
import signal

import uvicorn
from telegram import MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from backend.api import app as fastapi_app
from bot.handlers import (
    start, help_command, status_command, patterns_command,
    style_command, style_choice, reset_command, handle_voice,
    handle_message, app_command,
)
from bot.scheduler import setup_scheduler
from bot.memory.database import init_db
from shared.config import TELEGRAM_BOT_TOKEN, WEBAPP_URL

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _setup_bot() -> Application:
    """Создаёт и настраивает Telegram Application."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Инициализация БД
    await init_db()
    logger.info("БД инициализирована")

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("patterns", patterns_command))
    app.add_handler(CommandHandler("style", style_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("app", app_command))

    # Inline кнопки
    app.add_handler(CallbackQueryHandler(style_choice, pattern="^style_"))

    # Голосовые и текстовые сообщения
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Обработчик ошибок
    async def error_handler(update, context):
        logger.error(f"Exception: {context.error}", exc_info=context.error)

    app.add_error_handler(error_handler)

    # Планировщик
    setup_scheduler(app)

    # Инициализируем бота
    await app.initialize()
    await app.start()

    # Menu Button с Mini App
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

    # Запускаем polling
    await app.updater.start_polling(allowed_updates=["message", "callback_query"])
    logger.info("Telegram бот запущен (polling)")

    return app


async def _run_api():
    """Запускает FastAPI через uvicorn."""
    port = int(os.getenv("PORT", "8080"))
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    logger.info(f"FastAPI сервер запускается на порту {port}")
    await server.serve()


async def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    bot_app = await _setup_bot()

    try:
        await _run_api()
    finally:
        logger.info("Завершение работы...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
