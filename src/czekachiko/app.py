from collections.abc import Callable
from datetime import date

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from sqlalchemy.ext.asyncio import async_sessionmaker

from czekachiko.fsm_storage import PgStorage
from czekachiko.handlers import admin, cases, common, settings, stats
from czekachiko.middlewares import ConcurrencyMiddleware, DbMiddleware, ThrottleMiddleware


def build_dispatcher(
    factory: async_sessionmaker,
    clock: Callable[[], date] = date.today,
    admin_tg_id: int | None = None,
    calendar_url: str | None = None,
    throttle: bool = True,
) -> Dispatcher:
    dp = Dispatcher(
        storage=PgStorage(factory),
        # One update at a time per user: double taps run in order, never concurrently.
        events_isolation=SimpleEventIsolation(),
        clock=clock,
        admin_tg_id=admin_tg_id,
        calendar_url=calendar_url,
    )
    flood = ThrottleMiddleware() if throttle else None
    for observer in (dp.message, dp.callback_query):
        if flood is not None:
            observer.outer_middleware(flood)
        observer.outer_middleware(ConcurrencyMiddleware())
        observer.middleware(DbMiddleware(factory))
    routers = [
        admin.router,
        common.router,
        cases.router,
        stats.router,
        settings.router,
        common.fallback,
    ]
    for r in routers:
        # Module-level routers can belong to one dispatcher at a time; detach so tests
        # (and any rebuild) can create a fresh dispatcher.
        r._parent_router = None
    dp.include_routers(*routers)
    return dp
