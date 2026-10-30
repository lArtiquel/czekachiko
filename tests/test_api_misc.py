"""Profile, metadata, statistics, calendars and share queries over the API."""

from datetime import date, timedelta

from sqlalchemy import func, select

from czekachiko import share
from czekachiko.db import repo
from czekachiko.db.models import Case, CaseDocument, Feedback, User
from czekachiko.domain import PERMIT_GROUPS, Channel, Milestone, PermitType, Purpose, Voivodeship
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
        "permit_type": "temporary",
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


# --- permit types ----------------------------------------------------------------------


async def test_meta_groups_purposes_by_permit_type(api):
    meta = await api.json("GET", "/api/meta?lang=ru")
    assert [p["code"] for p in meta["purposes"]] == [
        "praca", "jdg", "blue_card", "studia", "rodzina", "inne", "staly", "rezydent_ue",
    ]  # fmt: skip
    assert meta["permit_types"] == [
        {
            "code": "temporary",
            "label": "временный побыт",
            "button": "Временный побыт (pobyt czasowy)",
            "purposes": ["praca", "jdg", "blue_card", "studia", "rodzina", "inne"],
        },
        {
            "code": "permanent",
            "label": "постоянный побыт",
            "button": "Постоянный побыт (pobyt stały)",
            "purposes": ["staly"],
        },
        {
            "code": "eu_resident",
            "label": "резидент ЕС",
            "button": "Резидент ЕС (rezydent długoterminowy UE)",
            "purposes": ["rezydent_ue"],
        },
    ]
    assert meta["checklists"]["blue_card"][-1] == {
        "code": "dyplom",
        "name": "Dyplom ukończenia studiów wyższych",
    }


async def _seed(session_factory, rows):
    """rows: (voivodeship, purpose, days from filing to fingerprints)."""
    async with session_factory() as s:
        for i, (voiv, purpose, days) in enumerate(rows):
            await repo.ensure_user(s, 3000 + i)
            filed = date(2026, 1, 1)
            c = await repo.create_case(s, 3000 + i, voiv, purpose, Channel.mos, filed, f"grp{i}")
            await repo.set_milestone(s, c, Milestone.fingerprints, filed + timedelta(days=days))
        await s.commit()


async def test_stats_for_bases_groups_and_all_of_poland(api, session_factory):
    V, P = Voivodeship, Purpose
    await _seed(
        session_factory,
        [
            (V.mazowieckie, P.praca, 100),
            (V.mazowieckie, P.praca, 120),
            (V.mazowieckie, P.jdg, 200),
            (V.mazowieckie, P.blue_card, 60),
            (V.malopolskie, P.praca, 300),
            (V.mazowieckie, P.staly, 400),
        ],
    )

    def fp(body):
        return body["chain"][2]["agg"]

    single = await api.json("GET", "/api/stats?voivodeship=mazowieckie&purpose=praca")
    assert fp(single) == {"n": 2, "mean": 110, "min": 100, "max": 120}
    # Several bases: pooled from intervals, not an average of medians.
    two = await api.json("GET", "/api/stats?voivodeship=mazowieckie&purpose=jdg,praca")
    assert fp(two) == {"n": 3, "mean": 140, "min": 100, "max": 200}
    group = await api.json("GET", "/api/stats?voivodeship=mazowieckie&group=temporary")
    assert fp(group) == {"n": 4, "mean": 120, "min": 60, "max": 200}
    poland = await api.json("GET", "/api/stats?group=temporary")
    assert fp(poland) == {"n": 5, "mean": 156, "min": 60, "max": 300}
    poland_praca = await api.json("GET", "/api/stats?purpose=praca")
    assert fp(poland_praca) == {"n": 3, "mean": 173, "min": 100, "max": 300}
    permanent = await api.json("GET", "/api/stats?group=permanent")
    assert fp(permanent) == {"n": 1, "mean": 400, "min": 400, "max": 400}
    assert permanent == await api.json("GET", "/api/stats?purpose=staly")
    assert set(group) == {"chain", "who_now"}


async def test_stats_validation(api):
    for query, fields in [
        ("voivodeship=mazowieckie", {"purpose": "invalid"}),
        ("voivodeship=&purpose=praca", {"voivodeship": "invalid"}),
        ("purpose=praca,visa", {"purpose": "invalid"}),
        ("purpose=praca,,jdg", {"purpose": "invalid"}),
        ("purpose=praca,staly", {"purpose": "mixed"}),
        ("group=forever", {"group": "invalid"}),
        ("group=temporary&purpose=praca", {"group": "exclusive"}),
        ("voivodeship=mars&group=", {"voivodeship": "invalid", "group": "invalid"}),
    ]:
        got = await api.json("GET", f"/api/stats?{query}", status=422)
        assert got == {"error": "invalid", "fields": fields}, query
    got = await api.json("GET", "/api/stats?voivodeship=nope&purpose=nope", status=422)
    assert list(got["fields"]) == ["voivodeship", "purpose"]  # same order as before


async def test_share_codes_for_new_selections(api):
    async def code(query):
        return (await api.json("GET", f"/api/share/stats?{query}"))["query"]

    # Old selections give exactly the old codes.
    assert await code("purpose=jdg&voivodeships=mazowieckie") == "s:jdg:6"
    assert await code("group=permanent&voivodeships=mazowieckie") == "s:staly:6"
    assert await code("group=temporary&voivodeships=all,mazowieckie") == "s:temporary:all,6"
    assert await code("purpose=jdg,praca,jdg&voivodeships=all") == "s:praca+jdg:all"
    every = ",".join(p.value for p in PERMIT_GROUPS[PermitType.temporary])
    assert await code(f"purpose={every}&voivodeships=lodzkie") == "s:temporary:4"
    assert share.decode("s:praca+jdg:all,6") == ("praca+jdg", [None, Voivodeship.mazowieckie])

    for query, fields in [
        ("purpose=praca,staly&voivodeships=all", {"purpose": "mixed"}),
        ("group=temporary&voivodeships=all,poland", {"voivodeships": "invalid"}),
        ("group=temporary&voivodeships=", {"voivodeships": "invalid"}),
        ("group=temporary&purpose=jdg&voivodeships=all", {"group": "exclusive"}),
    ]:
        got = await api.json("GET", f"/api/share/stats?{query}", status=422)
        assert got == {"error": "invalid", "fields": fields}, query
