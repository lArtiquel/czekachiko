import asyncio
import os
import uuid

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from czekachiko.db.session import run_migrations

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:55432/test"
)
TABLES = (
    "users, cases, milestones, aggregates, fsm, calendar_events, calendar_outbox, feedback, "
    "feedback_rate, case_documents"
)


@pytest.fixture(scope="session")
def db_url():
    name = f"t_{uuid.uuid4().hex[:10]}"
    admin = TEST_URL.replace("+asyncpg", "")

    async def execute(sql: str) -> None:
        conn = await asyncpg.connect(admin)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(execute(f"CREATE DATABASE {name}"))
    url = TEST_URL.rsplit("/", 1)[0] + "/" + name
    run_migrations(url)
    yield url
    asyncio.run(execute(f"DROP DATABASE {name} WITH (FORCE)"))


@pytest.fixture
async def session_factory(db_url):
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s
