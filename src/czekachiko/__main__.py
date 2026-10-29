import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from czekachiko.app import build_dispatcher
from czekachiko.config import Settings
from czekachiko.db.session import make_session_factory, run_migrations
from czekachiko.i18n import t

COMMANDS = ["start", "cases", "add", "stats", "calendar", "settings", "help", "cancel"]
log = logging.getLogger("czekachiko")


async def set_commands(bot: Bot) -> None:
    for lang, code in (("ru", None), ("ru", "ru"), ("en", "en")):
        cmds = [BotCommand(command=c, description=t(lang, f"cmd_{c}")) for c in COMMANDS]
        await bot.set_my_commands(cmds, language_code=code)


async def run(settings: Settings) -> None:
    engine, factory = make_session_factory(settings.database_url)
    bot = Bot(
        settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = build_dispatcher(
        factory, admin_tg_id=settings.admin_tg_id, calendar_url=settings.calendar_public_url
    )
    await set_commands(bot)
    tasks = []
    if settings.calendar_enabled:
        from czekachiko.calendar_sync import start_worker

        tasks.append(start_worker(settings, factory))
    try:
        await dp.start_polling(
            bot, allowed_updates=["message", "callback_query"], tasks_concurrency_limit=20
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
