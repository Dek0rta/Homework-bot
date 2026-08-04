"""
Точка входа. Поднимает aiogram-бота (long polling) и aiohttp-сервер,
который отдаёт health-check и REST API для Telegram Mini App.
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from src.api import webapp_api
from src.bot import handlers_group, handlers_private
from src.bot.backup import restore_if_empty
from src.core import db
from src.core.config import ADMIN_USER_ID, BOT_TOKEN, FSM_PATH
from src.core.storage import JsonStorage
from src.services import analytics
from src.services import calendar as calendar_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


PRIVATE_COMMANDS = [
    BotCommand(command="start",       description="Главное меню"),
    BotCommand(command="schedule",    description="Изменить расписание"),
    BotCommand(command="my_schedule", description="Посмотреть расписание"),
    BotCommand(command="stats",       description="График нагрузки класса"),
    BotCommand(command="backup",      description="Резервная копия расписания"),
    BotCommand(command="auth",        description="Подключить Google Calendar"),
    BotCommand(command="disconnect_calendar", description="Отвязать Google Calendar"),
    BotCommand(command="cancel",      description="Отменить текущее действие"),
    BotCommand(command="help",        description="Справка по командам"),
]

GROUP_COMMANDS = [
    BotCommand(command="hw",             description="Список домашних заданий"),
    BotCommand(command="stats",          description="График нагрузки класса"),
    BotCommand(command="export_csv",     description="Экспорт данных нагрузки в CSV"),
    BotCommand(command="setup_subjects", description="Настроить предметы (только admin)"),
    BotCommand(command="link_schedule",  description="Привязать расписание к группе (только admin)"),
    BotCommand(command="clear_hw",       description="Очистить список ДЗ (только admin)"),
    BotCommand(command="help",           description="Справка"),
]


async def start_http_server() -> None:
    """HTTP-сервер: health-check для хостинга + REST API для WebApp."""
    from aiohttp import web

    port = int(os.getenv("PORT", 8080))
    app  = web.Application()
    app.router.add_get("/", lambda _r: web.Response(text="OK"))
    webapp_api.setup_webapp_routes(app)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info("HTTP-сервер (health + WebApp API) запущен на порту %d", port)


async def main() -> None:
    # Порядок важен: analytics создаёт daily_load_metrics поверх схемы init_db.
    db.init_db()
    analytics.migrate_analytics_schema()
    restore_if_empty()

    # Старый общий data/token.json переезжает в БД как токен администратора.
    # До этого он использовался для всех пользователей сразу.
    calendar_api.migrate_legacy_token(ADMIN_USER_ID)

    # ДЗ, на которые за неделю никто не выбрал день сдачи
    stale = db.purge_stale_pending()
    if stale:
        logger.info("Удалено просроченных ожидающих ДЗ: %d", stale)

    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=JsonStorage(FSM_PATH))

    # Личные хендлеры первыми: их фильтры уже, групповые ловят остальное
    dp.include_router(handlers_private.router)
    dp.include_router(handlers_group.router)

    await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(GROUP_COMMANDS,   scope=BotCommandScopeAllGroupChats())

    logger.info("Бот запущен")
    await start_http_server()
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query", "channel_post"],
    )


if __name__ == "__main__":
    asyncio.run(main())
