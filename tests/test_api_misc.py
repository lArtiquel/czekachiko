"""Profile, metadata, statistics, calendars and share queries over the API."""

from datetime import date

from sqlalchemy import func, select

from czekachiko import share
from czekachiko.db import repo
from czekachiko.db.models import Case, CaseDocument, Feedback, User
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales import en, ru
from tests.test_api_cases import OTHER, create, seed_typical


async def test_me_and_language(api):
    assert await api.json("GET", "/api/me") == {"tg_id": 548, "lang": "ru", "reminders": False}
    assert (await api.json("PATCH", "/api/me", json={"lang": "en"}))["lang"] == "en"
    assert (await api.json("GET", "/api/me"))["lang"] == "en"
    assert await api.json("PATCH", "/api/me", status=422, json={"lang": "de"}) == {
        "error": "invalid",
        "fields": {"lang": "invalid"},
    }
    assert (await api.json("PATCH", "/api/me", json={}))["lang"] == "en"


async def test_delete_me_wipes_all_my_data(api, session_factory):
    case = await create(api)
    await api.json("POST", f"/api/cases/{case['id']}/documents", status=201, json={"name": "Mine"})
    await create(api, uid=OTHER, client_token="tok-theirs-1")
    async with session_factory() as s:
        await repo.add_feedback(s, 548, "in", "hello")
        await s.commit()

    assert await api.json("DELETE", "/api/me", status=204) is None

    async with session_factory() as s:

        async def count(model, *where):
            return await s.scalar(select(func.count()).select_from(model).where(*where))

        assert await count(Case, Case.tg_id == 548) == 0
        assert await count(CaseDocument) == 0
        assert await count(Feedback, Feedback.tg_id == 548) == 0
        assert await count(User, User.tg_id == 548) == 0
        assert await count(Case, Case.tg_id == OTHER) == 1
    assert await api.json("GET", "/api/cases") == []


async def test_meta_follows_requested_language(api):
    meta = await api.json("GET", "/api/meta?lang=en")
    assert len(meta["voivodeships"]) == 16
    assert meta["voivodeships"][0] == {"code": "dolnoslaskie", "label": "Dolnośląskie"}
    assert meta["purposes"][0] == {
        "code": "praca",
        "label": en.PURPOSE_LABELS[Purpose.praca],
        "button": en.PURPOSE_BUTTONS[Purpose.praca],
    }
    assert meta["channels"] == [{"code": c.value, "label": en.CHANNEL_LABELS[c]} for c in Channel]
    assert meta["milestones"][3] == {
        "code": "fingerprints",
        "label": en.MILESTONE_LABELS[Milestone.fingerprints],
        "hint": en.MILESTONE_HINTS[Milestone.fingerprints],
    }
    assert set(meta["checklists"]) == {p.value for p in Purpose}
    assert meta["checklists"]["studia"][-1] == {
        "code": "srodki",
        "name": "Środki finansowe (wyciąg z konta)",
    }
    assert meta["limits"] == {"max_cases": 5, "max_custom_docs": 15, "max_doc_name": 60}

    ru_meta = await api.json("GET", "/api/meta?lang=ru")
    assert ru_meta["purposes"][0]["label"] == ru.PURPOSE_LABELS[Purpose.praca]
    await api.json("PATCH", "/api/me", json={"lang": "en"})
    assert (await api.json("GET", "/api/meta"))["purposes"][0]["label"] == "work"
    assert await api.json("GET", "/api/meta?lang=de", status=422) == {
        "error": "invalid",
        "fields": {"lang": "invalid"},
    }


async def test_stats_chain_and_who_now(api, session_factory):
    await seed_typical(session_factory)
    async with session_factory() as s:  # three fingerprints in the last 30 days
        for i, filed in enumerate([date(2026, 1, 20), date(2026, 2, 3), date(2026, 3, 9)]):
            await repo.ensure_user(s, 2000 + i)
            c = await repo.create_case(
                s, 2000 + i, Voivodeship.mazowieckie, Purpose.jdg, Channel.mos, filed, f"now{i}"
            )
            await repo.set_milestone(s, c, Milestone.fingerprints, date(2026, 10, 10 + i))
        await s.commit()
    body = await api.json("GET", "/api/stats?voivodeship=mazowieckie&purpose=jdg")
    assert [c["milestone"] for c in body["chain"]][2] == "fingerprints"
    assert all(c["own_days"] is None for c in body["chain"])
    assert body["chain"][2]["agg"]["n"] == 11
    assert body["who_now"] == {"fingerprints": ["2026-01-01", "2026-03-01"], "decision": None}

    empty = await api.json("GET", "/api/stats?voivodeship=opolskie&purpose=studia")
    assert all(c["agg"] is None for c in empty["chain"])
    got = await api.json("GET", "/api/stats?voivodeship=x&purpose=", status=422)
    assert got == {"error": "invalid", "fields": {"voivodeship": "invalid", "purpose": "invalid"}}


async def test_calendars(api, session_factory):
    assert await api.json("GET", "/api/calendars") == []
    async with session_factory() as s:
        await repo.set_calendar(s, "slaskie", "s@group.calendar.google.com")
        await repo.set_calendar(s, "lodzkie", "l@group.calendar.google.com")
        await s.commit()
    body = await api.json("GET", "/api/calendars")
    assert [c["voivodeship"] for c in body] == ["lodzkie", "slaskie"]
    assert body[1]["label"] == "Śląskie"
    assert body[1]["url"] == (
        "https://calendar.google.com/calendar/embed?src=s%40group.calendar.google.com"
        "&ctz=Europe%2FWarsaw"
    )


async def test_share_case_query_is_owner_only(api):
    case = await create(api)
    assert await api.json("GET", f"/api/share/case/{case['id']}") == {"query": f"c:{case['id']}"}
    assert (await api.call("GET", f"/api/share/case/{case['id']}", uid=OTHER)).status == 404


async def test_share_stats_query(api):
    body = await api.json(
        "GET", "/api/share/stats?purpose=jdg&voivodeships=mazowieckie,malopolskie,mazowieckie"
    )
    voivs = [Voivodeship.mazowieckie, Voivodeship.malopolskie]
    assert body == {"query": share.encode("jdg", voivs)}
    assert share.decode(body["query"]) == ("jdg", voivs)

    seven = ",".join(v.value for v in list(Voivodeship)[:7])
    for query, fields in [
        (f"purpose=jdg&voivodeships={seven}", {"voivodeships": "too_many"}),
        ("purpose=jdg&voivodeships=mazowieckie,mars", {"voivodeships": "invalid"}),
        ("purpose=jdg&voivodeships=", {"voivodeships": "invalid"}),
        ("purpose=visa&voivodeships=opolskie", {"purpose": "invalid"}),
    ]:
        got = await api.json("GET", f"/api/share/stats?{query}", status=422)
        assert got == {"error": "invalid", "fields": fields}, query
