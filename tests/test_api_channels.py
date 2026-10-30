"""Filing channels over the API: picking, changing, and statistics split by channel."""

from datetime import date, timedelta

from sqlalchemy import select

from czekachiko.db import repo
from czekachiko.db.models import OutboxRow
from czekachiko.domain import USER_CHANNELS, Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales import ru
from tests.test_api_cases import OTHER, create

C, M = Channel, Milestone
FILED = date(2026, 1, 5)
POST_PATH = ["case_number", "braki", "fingerprints", "decision", "card"]
IN_PERSON_PATH = ["fingerprints", "case_number", "braki", "decision", "card"]


async def seed(session_factory, channel, days_list, start=0, voiv=Voivodeship.mazowieckie):
    """jdg cases filed on FILED, with fingerprints `days` later. Invented."""
    async with session_factory() as s:
        for i, days in enumerate(days_list, start):
            await repo.ensure_user(s, 3000 + i)
            c = await repo.create_case(s, 3000 + i, voiv, Purpose.jdg, channel, FILED, f"ch{i}")
            await repo.set_milestone(s, c, M.fingerprints, FILED + timedelta(days=days))
        await s.commit()


async def test_meta_lists_the_three_channels(api):
    meta = await api.json("GET", "/api/meta?lang=ru")
    assert meta["channels"] == [
        {"code": "in_person", "label": "Лично в urzędzie"},
        {"code": "post", "label": "Почта или e-Doręczenia"},
        {"code": "mos", "label": "MOS (онлайн)"},
    ]
    assert [c["code"] for c in meta["channels"]] == [c.value for c in USER_CHANNELS]


async def test_create_accepts_only_the_three_channels(api):
    for channel in ("in_person", "post", "mos"):
        case = await create(api, channel=channel, client_token=f"tok-{channel}-1")
        assert case["channel"] == channel
    for bad in ("paper", "unknown", "", None, 3):
        got = await api.json(
            "POST", "/api/cases", status=422, json={"voivodeship": "mazowieckie", "purpose": "jdg",
            "channel": bad, "filed": "2026-03-06", "client_token": "tok-bad-0001"},
        )  # fmt: skip
        assert got == {"error": "invalid", "fields": {"channel": "invalid"}}, bad


async def test_in_person_can_record_fingerprints_at_filing(api):
    case = await create(api, channel="in_person", fingerprints_at_filing=True)
    assert case["dates"] == {"filed": "2026-03-06", "fingerprints": "2026-03-06"}
    plain = await create(api, channel="in_person", client_token="tok-plain-01")
    assert plain["dates"] == {"filed": "2026-03-06"}
    off = await create(
        api, channel="in_person", fingerprints_at_filing=False, client_token="tok-off-0001"
    )
    assert off["dates"] == {"filed": "2026-03-06"}


async def test_a_retried_token_never_writes_fingerprints_onto_the_existing_case(api):
    # Same client token, different filing date: the existing case comes back untouched.
    first = await create(api, channel="in_person", client_token="tok-retry-001")
    assert first["dates"] == {"filed": "2026-03-06"}
    again = await create(
        api,
        channel="in_person",
        filed="2026-05-01",
        fingerprints_at_filing=True,
        client_token="tok-retry-001",
    )
    assert again["id"] == first["id"]
    assert again["dates"] == {"filed": "2026-03-06"}
    detail = await api.json("GET", f"/api/cases/{first['id']}")
    assert detail["dates"] == {"filed": "2026-03-06"}


async def test_a_retried_token_keeps_the_fingerprints_it_created(api):
    first = await create(
        api, channel="in_person", fingerprints_at_filing=True, client_token="tok-retry-002"
    )
    again = await create(
        api,
        channel="in_person",
        filed="2026-05-01",
        fingerprints_at_filing=True,
        client_token="tok-retry-002",
    )
    assert again["dates"] == first["dates"] == {"filed": "2026-03-06", "fingerprints": "2026-03-06"}


async def test_fingerprints_at_filing_is_only_for_in_person(api):
    for over in (
        {"channel": "post", "fingerprints_at_filing": True},
        {"channel": "in_person", "fingerprints_at_filing": "yes"},
    ):
        got = await create(api, status=422, **over)
        assert got == {"error": "invalid", "fields": {"fingerprints_at_filing": "invalid"}}


async def test_owner_changes_the_channel(api, session_factory):
    await seed(session_factory, C.mos, [80, 90])
    case = await create(api, filed="2025-12-01")
    url = f"/api/cases/{case['id']}"
    detail = await api.json("PATCH", url, json={"channel": "mos"})
    assert detail["channel"] == "mos"
    fp = next(c for c in detail["chain"] if c["milestone"] == "fingerprints")
    assert fp["agg"]["n"] == 2  # the MOS chain now
    assert (await api.json("GET", "/api/cases"))[0]["channel"] == "mos"
    async with session_factory() as s:
        mos = await repo.get_aggregate(s, "mazowieckie", "jdg", M.filed, M.fingerprints, C.mos)
    assert mos.n == 2
    # Calendar events name the channel, so they are rewritten.
    async with session_factory() as s:
        payloads = (
            await s.scalars(select(OutboxRow.payload).where(OutboxRow.case_id == case["id"]))
        ).all()
    assert payloads and all(" · MOS\n" in p["description"] for p in payloads)

    for bad in ({"channel": "unknown"}, {"channel": "paper"}, {}, {"channel": None}):
        got = await api.json("PATCH", url, status=422, json=bad)
        assert got == {"error": "invalid", "fields": {"channel": "invalid"}}, bad
    # Someone else's case is not found, as everywhere.
    assert await api.json("PATCH", url, status=404, uid=OTHER, json={"channel": "post"}) == {
        "error": "not_found"
    }


async def test_case_detail_follows_its_channel(api, session_factory):
    await seed(session_factory, C.in_person, [0, 0, 1])
    await seed(session_factory, C.post, [120, 140], start=3)
    case = await create(api, channel="in_person", filed="2026-10-01")
    detail = await api.json("GET", f"/api/cases/{case['id']}")
    assert [c["milestone"] for c in detail["chain"]] == IN_PERSON_PATH
    assert detail["chain"][0]["agg"] == {"n": 3, "mean": 0, "min": 0, "max": 1}
    # Three in-person cases are too few: the forecast uses every channel and says so. Four
    # weeks in, the three in-person cases already gave fingerprints sooner.
    f = detail["forecast"]
    assert (f["kind"], f["scope"], f["waited_longer_than"], f["total"]) == (
        "waited_longer",
        "voiv_any",
        3,
        5,
    )


async def test_stats_by_channel(api, session_factory):
    await seed(session_factory, C.in_person, [0, 0])
    await seed(session_factory, C.post, [120, 140, 160], start=2)
    async with session_factory() as s:
        await repo.ensure_user(s, repo.SYSTEM_TG_ID)
        dates = {M.filed: FILED, M.fingerprints: FILED + timedelta(days=60)}
        await repo.import_case(
            s, "pobytrack:1", Voivodeship.mazowieckie, Purpose.jdg, C.unknown, dates, "pobytrack"
        )
        await repo.recompute_for(s, "mazowieckie", "jdg")
        await s.commit()

    def fp(body):
        return next(c for c in body["chain"] if c["milestone"] == "fingerprints")["agg"]

    base = "/api/stats?voivodeship=mazowieckie&purpose=jdg"
    post = await api.json("GET", base + "&channel=post")
    assert [c["milestone"] for c in post["chain"]] == POST_PATH
    assert fp(post)["n"] == 3
    in_person = await api.json("GET", base + "&channel=in_person")
    assert [c["milestone"] for c in in_person["chain"]] == IN_PERSON_PATH
    assert fp(in_person) == {"n": 2, "mean": 0, "min": 0, "max": 0}
    assert in_person["who_now"]["fingerprints"] is None
    # Without a channel: every one, unknown included, in the milestone order.
    everything = await api.json("GET", base)
    assert [c["milestone"] for c in everything["chain"]] == POST_PATH
    assert fp(everything)["n"] == 6
    pooled = await api.json("GET", "/api/stats?group=temporary&channel=post")
    assert fp(pooled)["n"] == 3

    for bad in ("unknown", "paper", ""):
        got = await api.json("GET", f"{base}&channel={bad}", status=422)
        assert got == {"error": "invalid", "fields": {"channel": "invalid"}}, bad


def test_case_card_labels_are_unchanged_for_post():
    # Inline cards keep "Лично / почтой" for post: their text is pinned by the golden file.
    assert ru.CARD_CHANNEL_LABELS[C.post] == "Лично / почтой"
