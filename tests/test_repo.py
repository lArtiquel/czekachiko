from datetime import date

import pytest
from sqlalchemy import select

from czekachiko.db import repo
from czekachiko.db.models import OutboxRow
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship

M, V, P = Milestone, Voivodeship, Purpose


async def make_case(s, tg_id, token, filed=date(2026, 3, 6), voiv=V.mazowieckie, purpose=P.jdg):
    await repo.ensure_user(s, tg_id)
    return await repo.create_case(s, tg_id, voiv, purpose, Channel.paper, filed, token)


async def test_create_case_idempotent(session):
    a = await make_case(session, 1, "tok")
    b = await make_case(session, 1, "tok")
    await session.commit()
    assert a.id == b.id
    assert await repo.count_cases(session, 1) == 1


async def test_case_limit(session):
    for i in range(5):
        await make_case(session, 1, f"t{i}")
    with pytest.raises(repo.TooManyCases):
        await make_case(session, 1, "t5")


async def test_get_case_checks_owner(session):
    c = await make_case(session, 1, "tok")
    await session.commit()
    assert await repo.get_case(session, 2, c.id) is None
    assert (await repo.get_case(session, 1, c.id)).id == c.id


async def test_set_milestone_recomputes(session):
    for i in range(5):
        c = await make_case(session, 100 + i, f"t{i}")
        await repo.set_milestone(session, c, M.fingerprints, date(2026, 6, 1 + i))
    await session.commit()
    agg = await repo.get_aggregate(session, V.mazowieckie, P.jdg, M.filed, M.fingerprints)
    nat = await repo.get_aggregate(session, None, P.jdg, M.filed, M.fingerprints)
    assert agg.n == 5 and nat.n == 5
    assert agg.min == (date(2026, 6, 1) - date(2026, 3, 6)).days


async def test_interval_values_scopes(session):
    c1 = await make_case(session, 1, "a", voiv=V.mazowieckie)
    c2 = await make_case(session, 2, "b", voiv=V.malopolskie)
    await repo.set_milestone(session, c1, M.fingerprints, date(2026, 6, 4))
    await repo.set_milestone(session, c2, M.fingerprints, date(2026, 7, 4))
    await session.commit()
    voiv = await repo.interval_values(
        session, "voiv", V.mazowieckie, P.jdg, M.filed, M.fingerprints
    )
    nat = await repo.interval_values(
        session, "national", V.mazowieckie, P.jdg, M.filed, M.fingerprints
    )
    assert voiv == [90] and sorted(nat) == [90, 120]


async def test_delete_case_enqueues_calendar_deletes_and_recomputes(session):
    cases = []
    for i in range(5):
        c = await make_case(session, 100 + i, f"t{i}")
        await repo.set_milestone(session, c, M.fingerprints, date(2026, 6, 1))
        cases.append(c)
    await repo.record_event_id(session, cases[0].id, M.fingerprints, "evt-1")
    await session.commit()
    await repo.delete_case(session, cases[0])
    await session.commit()
    agg = await repo.get_aggregate(session, V.mazowieckie, P.jdg, M.filed, M.fingerprints)
    assert agg.n == 4
    rows = (await session.scalars(select(OutboxRow).where(OutboxRow.case_id == cases[0].id))).all()
    assert ("delete", "fingerprints") in [(r.op, r.milestone) for r in rows]
    assert not [r for r in rows if r.op == "upsert"]


async def test_delete_user_cascades(session):
    c = await make_case(session, 1, "tok")
    await repo.set_milestone(session, c, M.fingerprints, date(2026, 6, 1))
    await session.commit()
    await repo.delete_user(session, 1)
    await session.commit()
    assert await repo.count_cases(session, 1) == 0
    assert await repo.get_aggregate(session, V.mazowieckie, P.jdg, M.filed, M.fingerprints) is None


async def test_outbox_payload_is_anonymous(session):
    c = await make_case(session, 548, "tok")
    await repo.set_milestone(session, c, M.fingerprints, date(2026, 10, 29))
    await session.commit()
    row = (
        await session.scalars(
            select(OutboxRow).where(OutboxRow.milestone == "fingerprints", OutboxRow.op == "upsert")
        )
    ).first()
    assert row.payload["title"] == "Mazowieckie · art. 142 · отпечатки"
    assert row.payload["date"] == "2026-10-29"
    assert "03.2026" in row.payload["description"]
    assert "548" not in str(row.payload) and str(c.id) not in row.payload["description"]


async def test_recent_events(session):
    c = await make_case(session, 1, "tok")
    await repo.set_milestone(session, c, M.fingerprints, date(2026, 10, 20))
    await session.commit()
    ev = await repo.recent_events(session, V.mazowieckie, P.jdg, M.fingerprints, date(2026, 10, 1))
    assert ev == [(date(2026, 10, 20), date(2026, 3, 6))]


async def test_client_token_scoped_to_owner(session):
    await make_case(session, 1, "same-token")
    await session.commit()
    with pytest.raises(repo.TokenConflict):
        await make_case(session, 2, "same-token")


async def test_delete_case_enqueues_delete_for_every_milestone(session):
    c = await make_case(session, 1, "tok")
    await repo.set_milestone(session, c, M.fingerprints, date(2026, 6, 1))
    await session.commit()
    case_id = c.id
    await repo.delete_case(session, c)
    await session.commit()
    rows = (await session.scalars(select(OutboxRow).where(OutboxRow.case_id == case_id))).all()
    assert sorted((r.op, r.milestone) for r in rows) == [
        ("delete", "filed"),
        ("delete", "fingerprints"),
    ]
