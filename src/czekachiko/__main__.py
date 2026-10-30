import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from czekachiko.app import build_dispatcher
from czekachiko.config import Settings
from czekachiko.db.session import make_session_factory, run_migrations
from czekachiko.i18n import t
from czekachiko.middlewares import CONCURRENCY

log = logging.getLogger("czekachiko")


async def set_commands(bot: Bot) -> None:
    """Only /start: everything else lives in the Mini App. Replaces the old command lists."""
    for lang, code in (("ru", None), ("ru", "ru"), ("en", "en")):
        cmds = [BotCommand(command="start", description=t(lang, "cmd_start"))]
        await bot.set_my_commands(cmds, language_code=code)


async def set_menu_button(bot: Bot, url: str) -> None:
    """The button beside the input field opens the Mini App, in every private chat."""
    button = MenuButtonWebApp(text="Czekachiko", web_app=WebAppInfo(url=url))
    try:
        await bot.set_chat_menu_button(menu_button=button)
    except TelegramAPIError as e:  # a bad WEBAPP_URL must not keep the bot down
        log.warning("menu button not set: %s", e)


async def run(settings: Settings) -> None:
    engine, factory = make_session_factory(settings.database_url)
    bot = Bot(
        settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = build_dispatcher(
        factory,
        admin_tg_id=settings.admin_tg_id,
        webapp_url=settings.webapp_url,
    )
    await set_commands(bot)
    await set_menu_button(bot, settings.webapp_url)
    tasks = []
    if settings.calendar_enabled:
        from czekachiko.calendar_sync import start_worker

        task = start_worker(settings, factory)
        if task is not None:
            tasks.append(task)
    if settings.pobytrack_import:
        from czekachiko.importers.pobytrack import start_daily

        tasks.append(start_daily(factory))
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "inline_query"],
            tasks_concurrency_limit=CONCURRENCY,
        )
    finally:
        for task in tasks:
            task.cancel()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    run_migrations(settings.database_url)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
