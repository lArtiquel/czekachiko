import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from czekachiko.db.models import Base

target_metadata = Base.metadata


def do_run(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        # Bot and API both migrate on start; the lock makes the second one wait, then no-op.
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(7212345)")
        context.run_migrations()


async def run_online():
    engine = create_async_engine(context.config.get_main_option("sqlalchemy.url"))
    async with engine.connect() as conn:
        await conn.run_sync(do_run)
    await engine.dispose()


asyncio.run(run_online())
