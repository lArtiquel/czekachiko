"""Upgrading a database that already holds cases written by the previous release."""

import asyncio
import uuid
from datetime import date, timedelta

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


async def _seed_0007(url: str) -> None:
    """Cases as 0007 stored them: people's, and imported ones known only by their token."""
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        await conn.execute("INSERT INTO users (tg_id) VALUES (21), (-1)")
        for tg, token in [
            (21, "user-token-1"),
            (21, "tok-pobytrack-lookalike"),
            (-1, "pobytrack:103"),
            (-1, "pobytrack:204/2"),
        ]:
            await conn.execute(
                "INSERT INTO cases (tg_id, voivodeship, purpose, channel, client_token) "
                "VALUES ($1, 'mazowieckie', 'praca', 'paper', $2)",
                tg,
                token,
            )
    finally:
        await conn.close()


async def _sources(url: str) -> dict[str, str]:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch("SELECT client_token, source FROM cases")
        return {r["client_token"]: r["source"] for r in rows}
    finally:
        await conn.close()


def test_0008_backfills_the_source_of_existing_cases():
    name = f"t_mig_{uuid.uuid4().hex[:10]}"
    asyncio.run(_admin(f"CREATE DATABASE {name}"))
    url = TEST_URL.rsplit("/", 1)[0] + "/" + name
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    try:
        command.upgrade(cfg, "0007")
        asyncio.run(_seed_0007(url))
        command.upgrade(cfg, "head")
        assert asyncio.run(_sources(url)) == {
            "user-token-1": "user",
            "tok-pobytrack-lookalike": "user",
            "pobytrack:103": "pobytrack",
            "pobytrack:204/2": "pobytrack",
        }
        assert "ix_cases_source" in asyncio.run(_indexes(url))
        command.downgrade(cfg, "0007")
        assert "ix_cases_source" not in asyncio.run(_indexes(url))
        command.upgrade(cfg, "head")
        assert set(asyncio.run(_sources(url)).values()) == {"user", "pobytrack"}
    finally:
        asyncio.run(_admin(f"DROP DATABASE {name} WITH (FORCE)"))


# Cases as 0009 stored them: (tg_id, client token, source, channel, filed, fingerprints).
CASES_0009 = [
    (31, "user-paper-1", "user", "paper", date(2026, 1, 5), date(2026, 4, 20)),
    (31, "user-paper-2", "user", "paper", date(2026, 1, 12), date(2026, 5, 4)),
    (32, "user-mos-1", "user", "mos", date(2026, 2, 2), date(2026, 6, 15)),
    (-1, "pobytrack:501", "pobytrack", "paper", date(2026, 2, 16), date(2026, 7, 6)),
    (-1, "pobytrack:502", "pobytrack", "mos", date(2026, 3, 2), date(2026, 7, 27)),
]


async def _seed_0009(url: str) -> None:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        await conn.execute("INSERT INTO users (tg_id) VALUES (31), (32), (-1)")
        for tg, token, source, channel, filed, fp in CASES_0009:
            case_id = await conn.fetchval(
                "INSERT INTO cases (tg_id, voivodeship, purpose, channel, client_token, source) "
                "VALUES ($1, 'mazowieckie', 'jdg', $2, $3, $4) RETURNING id",
                tg,
                channel,
                token,
                source,
            )
            await conn.execute(
                "INSERT INTO milestones (case_id, milestone, date) "
                "VALUES ($1, 'filed', $2), ($1, 'fingerprints', $3)",
                case_id,
                filed,
                fp,
            )
        # A stale aggregate as 0009 left it: the upgrade recomputes every row.
        await conn.execute(
            "INSERT INTO aggregates (voivodeship, purpose, from_m, to_m, n, p10, median, p90, "
            "min, max, mean) VALUES ('mazowieckie', 'jdg', 'filed', 'fingerprints', "
            "1, 1, 1, 1, 1, 1, 1)"
        )
    finally:
        await conn.close()


async def _channels(url: str) -> dict[str, str]:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch("SELECT client_token, channel FROM cases")
        return {r["client_token"]: r["channel"] for r in rows}
    finally:
        await conn.close()


async def _fingerprint_aggregates(url: str) -> dict[tuple, tuple]:
    """(voivodeship, channel) -> (n, min, max) of filed → fingerprints for jdg."""
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            "SELECT voivodeship, channel, n, min, max, median FROM aggregates "
            "WHERE purpose = 'jdg' AND from_m = 'filed' AND to_m = 'fingerprints'"
        )
        return {(r["voivodeship"], r["channel"]): (r["n"], r["min"], r["max"]) for r in rows}
    finally:
        await conn.close()


async def _all_aggregates(url: str) -> set[tuple]:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            "SELECT voivodeship, purpose, channel, from_m, to_m, n, p10, median, p90, min, max, "
            "mean FROM aggregates"
        )
        return {tuple(round(v, 6) if isinstance(v, float) else v for v in r) for r in rows}
    finally:
        await conn.close()


async def _recompute_all(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as s:
            await repo.recompute_all(s)
            await s.commit()
    finally:
        await engine.dispose()


async def _columns(url: str, table: str) -> set[str]:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table
        )
        return {r["column_name"] for r in rows}
    finally:
        await conn.close()


def test_0010_splits_paper_and_aggregates_by_channel():
    name = f"t_mig_{uuid.uuid4().hex[:10]}"
    asyncio.run(_admin(f"CREATE DATABASE {name}"))
    url = TEST_URL.rsplit("/", 1)[0] + "/" + name
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    days = [(fp - filed).days for *_, filed, fp in CASES_0009]
    try:
        command.upgrade(cfg, "0009")
        asyncio.run(_seed_0009(url))
        command.upgrade(cfg, "head")
        # People's "paper" is post; imported "paper" waits for the importer to reclassify it.
        assert asyncio.run(_channels(url)) == {
            "user-paper-1": "post",
            "user-paper-2": "post",
            "user-mos-1": "mos",
            "pobytrack:501": "unknown",
            "pobytrack:502": "mos",
        }
        post, mos = days[:2], [days[2], days[4]]
        everything = (len(days), min(days), max(days))
        assert asyncio.run(_fingerprint_aggregates(url)) == {
            ("mazowieckie", None): everything,
            (None, None): everything,
            ("mazowieckie", "post"): (2, min(post), max(post)),
            (None, "post"): (2, min(post), max(post)),
            ("mazowieckie", "mos"): (2, min(mos), max(mos)),
            (None, "mos"): (2, min(mos), max(mos)),
        }
        # The SQL backfill writes exactly what the app's recompute writes.
        backfilled = asyncio.run(_all_aggregates(url))
        asyncio.run(_recompute_all(url))
        assert asyncio.run(_all_aggregates(url)) == backfilled

        command.downgrade(cfg, "0009")
        assert set(asyncio.run(_channels(url)).values()) == {"paper", "mos"}
        assert "channel" not in asyncio.run(_columns(url, "aggregates"))
        command.upgrade(cfg, "head")  # and back again
        assert asyncio.run(_channels(url))["user-paper-1"] == "post"
    finally:
        asyncio.run(_admin(f"DROP DATABASE {name} WITH (FORCE)"))


# Cases as 0010 stored them: (tg_id, token, channel, filed, {milestone: days from filing}).
CASES_0010 = [
    (41, "post-typo", "post", date(2026, 1, 5), {"case_number": 0, "fingerprints": 0}),
    (41, "post-real", "post", date(2026, 1, 12), {"case_number": 25, "fingerprints": 110}),
    (42, "counter", "in_person", date(2026, 2, 2), {"fingerprints": 0, "braki": 0}),
    (-1, "pobytrack:601", "unknown", date(2026, 2, 16), {"fingerprints": 0}),
]


async def _seed_0010(url: str) -> None:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        await conn.execute("INSERT INTO users (tg_id) VALUES (41), (42), (-1)")
        for tg, token, channel, filed, days in CASES_0010:
            source = "pobytrack" if tg == -1 else "user"
            case_id = await conn.fetchval(
                "INSERT INTO cases (tg_id, voivodeship, purpose, channel, client_token, source) "
                "VALUES ($1, 'mazowieckie', 'jdg', $2, $3, $4) RETURNING id",
                tg,
                channel,
                token,
                source,
            )
            rows = [("filed", filed)] + [(m, filed + timedelta(days=d)) for m, d in days.items()]
            for m, d in rows:
                await conn.execute(
                    "INSERT INTO milestones (case_id, milestone, date) VALUES ($1, $2, $3)",
                    case_id,
                    m,
                    d,
                )
        # A row as 0010 computed it, zeros included: the upgrade recomputes every row.
        await conn.execute(
            "INSERT INTO aggregates (voivodeship, purpose, channel, from_m, to_m, n, p10, "
            "median, p90, min, max, mean) VALUES ('mazowieckie', 'jdg', 'post', 'filed', "
            "'fingerprints', 2, 11, 55, 99, 0, 110, 55)"
        )
    finally:
        await conn.close()


async def _filed_aggregates(url: str) -> dict[tuple, tuple]:
    """(voivodeship, channel, to_m) -> (n, min, max) of jdg intervals from filing."""
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = await conn.fetch(
            "SELECT voivodeship, channel, to_m, n, min, max FROM aggregates "
            "WHERE purpose = 'jdg' AND from_m = 'filed'"
        )
        return {
            (r["voivodeship"], r["channel"], r["to_m"]): (r["n"], r["min"], r["max"]) for r in rows
        }
    finally:
        await conn.close()


async def _milestone_count(url: str) -> int:
    conn = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        return await conn.fetchval("SELECT count(*) FROM milestones")
    finally:
        await conn.close()


def test_0011_drops_impossible_zero_days_from_aggregates():
    name = f"t_mig_{uuid.uuid4().hex[:10]}"
    asyncio.run(_admin(f"CREATE DATABASE {name}"))
    url = TEST_URL.rsplit("/", 1)[0] + "/" + name
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    try:
        command.upgrade(cfg, "0010")
        asyncio.run(_seed_0010(url))
        stored = asyncio.run(_milestone_count(url))
        command.upgrade(cfg, "head")
        got = asyncio.run(_filed_aggregates(url))
        assert got[("mazowieckie", "post", "fingerprints")] == (1, 110, 110)
        assert got[("mazowieckie", "post", "case_number")] == (1, 25, 25)
        assert got[("mazowieckie", "in_person", "fingerprints")] == (1, 0, 0)  # at the counter
        assert ("mazowieckie", "in_person", "braki") not in got
        assert got[("mazowieckie", None, "fingerprints")] == (2, 0, 110)  # unknown's 0 is out
        assert got[(None, None, "fingerprints")] == (2, 0, 110)
        assert asyncio.run(_milestone_count(url)) == stored  # no date is touched
        # The SQL backfill writes exactly what the app's recompute writes.
        backfilled = asyncio.run(_all_aggregates(url))
        asyncio.run(_recompute_all(url))
        assert asyncio.run(_all_aggregates(url)) == backfilled

        command.downgrade(cfg, "0010")
        assert asyncio.run(_filed_aggregates(url))[("mazowieckie", "post", "fingerprints")] == (
            2,
            0,
            110,
        )
        command.upgrade(cfg, "head")  # and back again
        assert asyncio.run(_all_aggregates(url)) == backfilled
    finally:
        asyncio.run(_admin(f"DROP DATABASE {name} WITH (FORCE)"))
