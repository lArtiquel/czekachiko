"""Upgrading a database that already holds cases written by the previous release."""

import asyncio
import uuid
from datetime import date

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from czekachiko.db import repo
from czekachiko.db.session import MIGRATIONS
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from tests.conftest import TEST_URL

M = Milestone
ADMIN = TEST_URL.replace("+asyncpg", "")

# Rows exactly as release 0006 wrote them: (tg_id, voivodeship, purpose, filed, fingerprints).
OLD_CASES = [
    (11, "mazowieckie", "jdg", date(2026, 1, 5), date(2026, 4, 20)),
    (12, "mazowieckie", "jdg", date(2026, 1, 12), date(2026, 5, 4)),
    (13, "mazowieckie", "praca", date(2026, 2, 2), date(2026, 6, 15)),
    (14, "malopolskie", "rodzina", date(2026, 2, 16), None),
    (15, "slaskie", "studia", date(2026, 3, 2), date(2026, 7, 27)),
    (16, "slaskie", "inne", date(2026, 3, 9), None),
]


async def _admin(sql: str) -> None:
    conn = await asyncpg.connect(ADMIN)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _seed_old(url: str) -> None:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        for i, (tg, voiv, purpose, filed, fp) in enumerate(OLD_CASES):
            await conn.execute("INSERT INTO users (tg_id) VALUES ($1)", tg)
            case_id = await conn.fetchval(
                "INSERT INTO cases (tg_id, voivodeship, purpose, channel, client_token) "
                "VALUES ($1, $2, $3, 'paper', $4) RETURNING id",
                tg,
                voiv,
                purpose,
                f"old-token-{i}",
            )
            await conn.execute(
                "INSERT INTO milestones (case_id, milestone, date) VALUES ($1, 'filed', $2)",
                case_id,
                filed,
            )
            if fp is not None:
                await conn.execute(
                    "INSERT INTO milestones (case_id, milestone, date) "
                    "VALUES ($1, 'fingerprints', $2)",
                    case_id,
                    fp,
                )
        # An aggregate row as 0006 stored it, so the upgrade must leave it readable.
        await conn.execute(
            "INSERT INTO aggregates (voivodeship, purpose, from_m, to_m, n, p10, median, p90, "
            "min, max, mean) VALUES ('mazowieckie', 'jdg', 'filed', 'fingerprints', "
            "2, 105.7, 108.5, 111.3, 105, 112, 108.5)"
        )
    finally:
        await conn.close()


async def _indexes(url: str) -> set[str]:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        return {r["indexname"] for r in rows}
    finally:
        await conn.close()


async def _check_upgraded(url: str) -> None:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as s:
            cases = [c for tg, *_ in OLD_CASES for c in await repo.list_cases(s, tg)]
            assert [(c.voivodeship, c.purpose) for c in cases] == [
                (v, p) for _, v, p, _, _ in OLD_CASES
            ]
            assert all(Purpose(c.purpose) and Voivodeship(c.voivodeship) for c in cases)
            assert cases[0].dates() == {
                M.filed: date(2026, 1, 5),
                M.fingerprints: date(2026, 4, 20),
            }

            stored = await repo.get_aggregate(s, "mazowieckie", "jdg", M.filed, M.fingerprints)
            assert (stored.n, stored.min, stored.max, stored.median) == (2, 105, 112, 108.5)
            await repo.recompute_all(s)
            again = await repo.get_aggregate(s, "mazowieckie", "jdg", M.filed, M.fingerprints)
            assert (again.n, again.min, again.max, again.median) == (2, 105, 112, 108.5)

            # A case under a new basis lands next to the old ones.
            await repo.ensure_user(s, 99)
            new = await repo.create_case(
                s,
                99,
                Voivodeship.mazowieckie,
                Purpose.blue_card,
                Channel.mos,
                date(2026, 3, 1),
                "new-token-1",
            )
            assert new.purpose == "blue_card"
            await s.commit()
    finally:
        await engine.dispose()


def test_upgrade_from_0006_keeps_existing_cases():
    name = f"t_mig_{uuid.uuid4().hex[:10]}"
    asyncio.run(_admin(f"CREATE DATABASE {name}"))
    url = TEST_URL.rsplit("/", 1)[0] + "/" + name
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    try:
        command.upgrade(cfg, "0006")
        asyncio.run(_seed_old(url))
        command.upgrade(cfg, "head")
        assert {"ix_cases_purpose_voivodeship", "ix_milestones_milestone_date"} <= asyncio.run(
            _indexes(url)
        )
        asyncio.run(_check_upgraded(url))

        command.downgrade(cfg, "0006")
        assert "ix_cases_purpose_voivodeship" not in asyncio.run(_indexes(url))
        command.upgrade(cfg, "head")  # and back again
    finally:
        asyncio.run(_admin(f"DROP DATABASE {name} WITH (FORCE)"))
