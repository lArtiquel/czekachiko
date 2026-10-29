from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

POOL_SIZE = 8
MAX_OVERFLOW = 4
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def make_session_factory(
    url: str, pool_size: int = POOL_SIZE, max_overflow: int = MAX_OVERFLOW, api: bool = False
) -> tuple[AsyncEngine, async_sessionmaker]:
    """`api=True`: fail fast instead of queueing — short pool wait and server-side timeouts."""
    kwargs: dict = {}
    if api:
        kwargs = {
            "pool_timeout": 5,
            "connect_args": {
                "server_settings": {
                    "statement_timeout": "5000",
                    "lock_timeout": "5000",
                    "idle_in_transaction_session_timeout": "10000",
                }
            },
        }
    engine = create_async_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        hide_parameters=True,  # never put bound values (document names…) in error logs
        **kwargs,
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def run_migrations(url: str) -> None:
    """Synchronous; call before the event loop starts."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
