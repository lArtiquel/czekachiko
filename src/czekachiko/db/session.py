from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[3]


def make_session_factory(url: str) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def run_migrations(url: str) -> None:
    """Synchronous; call before the event loop starts."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
