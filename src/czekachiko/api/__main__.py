import logging

from aiohttp import web

from czekachiko.api.app import create_app
from czekachiko.config import Settings
from czekachiko.db.session import make_session_factory, run_migrations

# The bot holds up to 12 connections; Postgres allows 20 (see docker-compose.yml).
POOL_SIZE = 4
MAX_OVERFLOW = 2
# No headers: the Authorization header carries the user's initData.
ACCESS_LOG = '%a "%r" %s %b %Tf'


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    run_migrations(settings.database_url)
    engine, factory = make_session_factory(
        settings.database_url, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW, api=True
    )
    app = create_app(settings, factory)

    async def dispose(_: web.Application) -> None:
        await engine.dispose()

    app.on_cleanup.append(dispose)
    web.run_app(app, host="0.0.0.0", port=8080, access_log_format=ACCESS_LOG, print=None)


if __name__ == "__main__":
    main()
