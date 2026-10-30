"""Cases and milestones over the API: CRUD, ownership, validation, outliers, forecasts."""

import asyncio
from datetime import date, timedelta

from sqlalchemy import func, select

from czekachiko.db import repo
from czekachiko.db.models import MilestoneRow, OutboxRow
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship

NEW = {
    "voivodeship": "mazowieckie",
    "purpose": "jdg",
    "channel": "post",
    "filed": "2026-03-06",
    "client_token": "tok-00000001",
}
OTHER = 999


async def create(api, status: int = 201, uid: int | None = None, **over):
    return await api.json("POST", "/api/cases", status=status, uid=uid, json={**NEW, **over})


async def seed_typical(session_factory, filed=date(2025, 1, 1)):
    """Eight jdg cases in Mazowieckie: filing to fingerprints took 90..240 days."""
    async with session_factory() as s:
        for i, days in enumerate([90, 100, 120, 150, 170, 190, 210, 240]):
            await repo.ensure_user(s, 1000 + i)
            c = await repo.create_case(
                s, 1000 + i, Voivodeship.mazowieckie, Purpose.jdg, Channel.mos, filed, f"seed{i}"
            )
            await repo.set_milestone(s, c, Milestone.fingerprints, filed + timedelta(days=days))
        await s.commit()


async def test_case_crud_happy_path(api):
    assert await api.json("GET", "/api/cases") == []
    case = await create(api)
    assert case == {
        "id": case["id"],
        "voivodeship": "mazowieckie",
        "purpose": "jdg",
        "channel": "post",
        "dates": {"filed": "2026-03-06"},
        "docs_done": 0,
        "docs_total": 9,
    }
    assert await api.json("GET", "/api/cases") == [case]

    detail = await api.json("GET", f"/api/cases/{case['id']}")
    assert {k: detail[k] for k in case} == case
    assert [c["milestone"] for c in detail["chain"]] == [
        "case_number",
        "braki",
        "fingerprints",
        "decision",
        "card",
    ]
    assert all(c["own_days"] is None and c["agg"] is None for c in detail["chain"])
    assert detail["forecast"]["kind"] == "no_data"
    assert detail["forecast"]["target"] == "fingerprints"
    assert detail["documents"][0] == {
        "id": None,
        "code": "wniosek",
        "name": "Wniosek",
        "date": None,
        "custom": False,
    }
    assert len(detail["documents"]) == 9

    assert await api.json("DELETE", f"/api/cases/{case['id']}", status=204) is None
    assert await api.json("GET", f"/api/cases/{case['id']}", status=404) == {"error": "not_found"}
    assert await api.json("GET", "/api/cases") == []


async def test_create_is_idempotent_by_client_token(api):
    a = await create(api)
    b = await create(api)
    assert a["id"] == b["id"]
    assert len(await api.json("GET", "/api/cases")) == 1


async def test_concurrent_double_submit_creates_one_case(api):
    results = await asyncio.gather(*(api.call("POST", "/api/cases", json=NEW) for _ in range(3)))
    assert [r.status for r in results] == [201, 201, 201]
    assert len({(await r.json())["id"] for r in results}) == 1


async def test_case_limit_is_409(api):
    for i in range(5):
        await create(api, client_token=f"tok-limit-{i}")
    assert await create(api, status=409, client_token="tok-limit-5") == {"error": "too_many_cases"}


async def test_case_limit_holds_under_concurrent_creates(api):
    for i in range(4):
        await create(api, client_token=f"tok-race-{i}")
    results = await asyncio.gather(
        *(
            api.call("POST", "/api/cases", json={**NEW, "client_token": f"tok-new-{i}"})
            for i in range(3)
        )
    )
    assert sorted(r.status for r in results) == [201, 409, 409]


async def test_create_validates_every_field(api):
    bad = {"voivodeship": "mars", "purpose": 1, "channel": None, "filed": "06.03.2026"}
    body = await api.json("POST", "/api/cases", status=422, json={**bad, "client_token": "x"})
    assert body == {
        "error": "invalid",
        "fields": {
            "voivodeship": "invalid",
            "purpose": "invalid",
            "channel": "invalid",
            "filed": "not_date",
            "client_token": "invalid",
        },
    }
    assert (await create(api, status=422, filed="2026-10-30"))["fields"] == {"filed": "future"}
    assert (await create(api, status=422, filed="2014-12-31"))["fields"] == {"filed": "before_2015"}
    assert (await create(api, status=422, filed="2026-02-30"))["fields"] == {"filed": "not_date"}
    assert await api.json("GET", "/api/cases") == []


async def test_client_token_of_another_user_is_rejected(api):
    await create(api, uid=OTHER)
    body = await create(api, status=422)
    assert body == {"error": "invalid", "fields": {"client_token": "taken"}}


async def test_another_users_case_is_404_everywhere(api):
    case_id = (await create(api, uid=OTHER))["id"]
    base = f"/api/cases/{case_id}"
    calls = [
        ("GET", base, None),
        ("DELETE", base, None),
        ("PUT", f"{base}/milestones/fingerprints", {"date": "2026-08-01"}),
        ("DELETE", f"{base}/milestones/fingerprints", None),
        ("PUT", f"{base}/documents/std/wniosek", {"date": "2026-03-06"}),
        ("POST", f"{base}/documents", {"name": "X", "date": None}),
        ("GET", f"/api/share/case/{case_id}", None),
    ]
    for method, path, body in calls:
        assert await api.json(method, path, status=404, json=body) == {"error": "not_found"}, path
    assert (await api.json("GET", base, uid=OTHER))["id"] == case_id  # untouched


async def test_huge_or_odd_ids_are_404(api):
    for path in ("/api/cases/99999999999999999999", "/api/cases/-1", "/api/cases/abc"):
        assert (await api.call("GET", path)).status == 404, path


async def test_set_and_clear_milestone(api, session_factory):
    case = await create(api)
    url = f"/api/cases/{case['id']}/milestones/fingerprints"
    detail = await api.json("PUT", url, json={"date": "2026-08-01"})
    assert detail["dates"] == {"filed": "2026-03-06", "fingerprints": "2026-08-01"}
    fp = next(c for c in detail["chain"] if c["milestone"] == "fingerprints")
    assert fp["own_days"] == 148
    assert fp["agg"] == {"n": 1, "mean": 148, "min": 148, "max": 148}  # aggregates recomputed
    async with session_factory() as s:
        ops = (await s.scalars(select(OutboxRow.op).where(OutboxRow.case_id == case["id"]))).all()
    assert sorted(ops) == ["upsert", "upsert"]  # the calendar outbox fills as from the bot

    detail = await api.json("DELETE", url)
    assert detail["dates"] == {"filed": "2026-03-06"}
    async with session_factory() as s:
        deletes = await s.scalar(
            select(func.count()).select_from(OutboxRow).where(OutboxRow.op == "delete")
        )
    assert deletes == 1
    assert (await api.json("DELETE", url))["dates"] == {"filed": "2026-03-06"}  # idempotent


async def test_filed_can_change_but_not_be_removed(api):
    case = await create(api)
    url = f"/api/cases/{case['id']}/milestones/filed"
    assert (await api.json("PUT", url, json={"date": "2026-03-01"}))["dates"]["filed"] == (
        "2026-03-01"
    )
    assert await api.json("DELETE", url, status=422) == {
        "error": "invalid",
        "codes": ["filed_missing"],
    }


async def test_unknown_milestone_is_404(api):
    case = await create(api)
    url = f"/api/cases/{case['id']}/milestones/visa"
    assert (await api.call("PUT", url, json={"date": "2026-08-01"})).status == 404


async def test_milestone_rules_give_422_codes(api):
    case = await create(api)
    base = f"/api/cases/{case['id']}/milestones"
    await api.json("PUT", f"{base}/decision", json={"date": "2026-09-01"})
    cases = [
        ("fingerprints", {"date": "2026-02-01"}, ["before_filed"]),
        ("fingerprints", {"date": "2026-10-30"}, ["future", "order"]),
        ("card", {"date": "2026-08-01"}, ["order"]),
        ("fingerprints", {"date": "1.8.2026"}, ["not_date"]),
        ("fingerprints", {}, ["not_date"]),
    ]
    for m, body, codes in cases:
        got = await api.json("PUT", f"{base}/{m}", status=422, json=body)
        assert got == {"error": "invalid", "codes": codes}, (m, body)
    got = await api.json(
        "PUT", f"{base}/fingerprints", status=422, json={"date": "2026-08-01", "confirm_outlier": 1}
    )
    assert got == {"error": "invalid", "fields": {"confirm_outlier": "invalid"}}


async def test_outlier_needs_confirmation(api, session_factory):
    await seed_typical(session_factory)
    case = await create(api, filed="2024-12-01")
    url = f"/api/cases/{case['id']}/milestones/fingerprints"
    body = await api.json("PUT", url, status=409, json={"date": "2026-08-03"})
    assert body["error"] == "outlier" and body["value"] == 610
    assert body["typical"] == {"p10": 97, "p90": 219}
    assert (body["from"], body["to"]) == ("filed", "fingerprints")
    detail = await api.json("PUT", url, json={"date": "2026-08-03", "confirm_outlier": True})
    assert detail["dates"]["fingerprints"] == "2026-08-03"
    async with session_factory() as s:
        row = await s.get(MilestoneRow, (case["id"], "fingerprints"))
    assert row.confirmed_outlier is True


async def test_ordinary_value_is_saved_unconfirmed(api, session_factory):
    await seed_typical(session_factory)
    case = await create(api, filed="2026-01-01")
    url = f"/api/cases/{case['id']}/milestones/fingerprints"
    await api.json("PUT", url, json={"date": "2026-05-01", "confirm_outlier": True})
    async with session_factory() as s:
        assert (await s.get(MilestoneRow, (case["id"], "fingerprints"))).confirmed_outlier is False


async def test_detail_has_forecast_window_and_typical_chain(api, session_factory):
    await seed_typical(session_factory)
    case = await create(api, filed="2026-07-01")
    detail = await api.json("GET", f"/api/cases/{case['id']}")
    assert detail["forecast"] == {
        "kind": "window",
        "target": "fingerprints",
        "start": "2026-11-13",
        "likely": "2026-12-28",
        "end": "2027-02-11",
        "n": 6,
        "scope": "voiv",
        "waited_longer_than": None,
        "total": None,
        "fastest": 90,
        "slowest": 240,
    }
    fp = next(c for c in detail["chain"] if c["milestone"] == "fingerprints")
    assert fp == {
        "milestone": "fingerprints",
        "own_days": None,
        "agg": {"n": 8, "mean": 159, "min": 90, "max": 240},
    }


async def test_detail_forecast_matches_the_bot(api, session_factory):
    from czekachiko.forecasting import case_forecast

    await seed_typical(session_factory)
    case = await create(api, filed="2025-11-01")
    detail = await api.json("GET", f"/api/cases/{case['id']}")
    async with session_factory() as s:
        f = await case_forecast(s, await repo.get_case(s, 548, case["id"]), date(2026, 10, 29))
    assert detail["forecast"]["kind"] == f.kind == "waited_longer"
    assert detail["forecast"]["waited_longer_than"] == f.waited_longer_than
    assert detail["forecast"]["total"] == f.total == 8
