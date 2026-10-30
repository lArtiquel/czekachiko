"""The pobyt-tracker importer: parsing the site bundle, mapping, upserts, failures, schedule."""

import copy
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from czekachiko.db import repo
from czekachiko.db.models import AggregateRow, Case, OutboxRow
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.importers import pobytrack as pt
from tests.fakes import sign_init_data, text_update

FIXTURE = Path(__file__).parent / "fixtures" / "pobytrack-site-sample.js"
TODAY = date(2026, 10, 30)
M, P, V = Milestone, Purpose, Voivodeship


def sample() -> dict:
    return pt.extract_dataset(FIXTURE.read_text(encoding="utf-8"))


def case_dict(**kw) -> dict:
    base = {
        "region": "mazowieckie",
        "post": 9001,
        "basis": "work",
        "method": "mos2",
        "submitted": "2026-01-10",
        "call": None,
        "fingerprints": None,
        "decision": None,
        "card": None,
        "approx": False,
        "source": "parser",
        "reported": "2026-02-01",
        "contacts": [],
        "planned": [],
    }
    return base | kw


# --- parsing ---------------------------------------------------------------------------


def test_parses_the_real_bundle():
    data = sample()
    assert (data["generated"], data["lastPost"], len(data["cases"])) == ("2026-10-29", 4284, 21)
    first = data["cases"][0]
    assert first == {
        "region": "dolnośląskie",
        "post": 103,
        "basis": "jdg",
        "method": "mos2",
        "submitted": "2026-03-17",
        "call": None,
        "fingerprints": None,
        "decision": None,
        "card": None,
        "approx": False,
        "source": "parser",
        "reported": "2026-05-12",
        "contacts": [],
        "planned": [],
    }
    posts = [c["post"] for c in data["cases"]]
    assert 1000 in posts and all(type(p) is int for p in posts)  # written as 1e3
    assert any(c["approx"] is True for c in data["cases"])
    assert any(c["contacts"] and isinstance(c["contacts"][0], list) for c in data["cases"])


def test_literal_reader_edges():
    read = lambda text: pt._Literal(text).value()  # noqa: E731
    assert read('{"a b":"x\\ny",\'c\':`d\\u0105`,e:!0,f:-1.5,g:[],h:true}') == {
        "a b": "x\ny",
        "c": "dą",
        "e": True,
        "f": -1.5,
        "g": [],
        "h": True,
    }
    for bad in ("{a:`${x}`}", "{a:void 0}", "{a:1", "{a:`x}", "{a:!2}", "[1 2]"):
        with pytest.raises(pt.DatasetError):
            read(bad)


def test_bundle_without_dataset_is_refused():
    with pytest.raises(pt.DatasetError):
        pt.extract_dataset("var x={a:1};")
    with pytest.raises(pt.DatasetError):
        pt.extract_dataset("var tr={generated:`x`,lastPost:1,cases:[]}")
    with pytest.raises(pt.DatasetError):
        pt.check_dataset({"generated": "x"})


def test_load_file_reads_json_and_bundles(tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps(sample()), encoding="utf-8")
    assert pt.load_file(path) == sample() == pt.load_file(FIXTURE)
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(pt.DatasetError):
        pt.load_file(tmp_path / "bad.json")


# --- sources ---------------------------------------------------------------------------


def transport(routes: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.MockTransport(handler)


async def test_fetch_follows_the_page_to_its_bundle():
    page = '<link rel="modulepreload" href="/assets/site-tgGUVGp3.js" fetchPriority="low"/>'
    routes = {
        pt.SITE_URL: httpx.Response(200, text=page),
        "https://pobyt-tracker.pages.dev/assets/site-tgGUVGp3.js": httpx.Response(
            200, text=FIXTURE.read_text(encoding="utf-8")
        ),
        "https://data.example/pobyt.json": httpx.Response(200, json=sample()),
    }
    async with httpx.AsyncClient(transport=transport(routes)) as client:
        assert await pt.fetch_dataset(client=client) == sample()
        assert await pt.fetch_dataset("https://data.example/pobyt.json", client=client) == sample()
        with pytest.raises(httpx.HTTPStatusError):
            await pt.fetch_dataset("https://data.example/missing.json", client=client)


async def test_fetch_refuses_pages_without_a_bundle_and_huge_files(monkeypatch):
    routes = {pt.SITE_URL: httpx.Response(200, text="<html>maintenance</html>")}
    async with httpx.AsyncClient(transport=transport(routes)) as client:
        with pytest.raises(pt.DatasetError):
            await pt.fetch_dataset(client=client)
    monkeypatch.setattr(pt, "MAX_BYTES", 10)
    routes = {"https://data.example/a.json": httpx.Response(200, text="x" * 100)}
    async with httpx.AsyncClient(transport=transport(routes)) as client:
        with pytest.raises(pt.DatasetError):
            await pt.fetch_dataset("https://data.example/a.json", client=client)


# --- mapping ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "voiv"),
    [
        ("dolnośląskie", V.dolnoslaskie),
        ("łódzkie", V.lodzkie),
        ("śląskie", V.slaskie),
        ("kujawsko-pomorskie", V.kujawsko_pomorskie),
        ("Warmińsko-Mazurskie", V.warminsko_mazurskie),
        ("mars", None),
        (None, None),
    ],
)
def test_regions(name, voiv):
    assert pt.region_of(name) == voiv


def test_maps_bases_methods_and_dates():
    expected = {
        "work": P.praca,
        "jdg": P.jdg,
        "bc": P.blue_card,
        "fam": P.rodzina,
        "study": P.studia,
        "temp": P.inne,
        "res": P.rezydent_ue,
        "perm": P.staly,
    }
    for basis, purpose in expected.items():
        assert pt.map_case(case_dict(basis=basis), TODAY).purpose == purpose
    for method, channel in [("mos2", "mos"), ("personal", "paper"), ("post", "paper"),
                            ("edor", "paper"), ("unk", "paper"), (None, "paper")]:  # fmt: skip
        assert pt.map_case(case_dict(method=method), TODAY).channel == channel
    row = pt.map_case(
        case_dict(call="2026-02-01", fingerprints="2026-03-01", decision="2026-06-01"), TODAY
    )
    assert row == pt.Row(
        "9001",
        V.mazowieckie,
        P.praca,
        Channel.mos,
        {M.filed: date(2026, 1, 10), M.braki: date(2026, 2, 1),
         M.fingerprints: date(2026, 3, 1), M.decision: date(2026, 6, 1)},
    )  # fmt: skip


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"basis": "other"}, "basis_other"),
        ({"basis": "visa"}, "basis_unknown"),
        ({"region": "bawaria"}, "region_unknown"),
        ({"post": 0}, "post_invalid"),
        ({"post": "12"}, "post_invalid"),
        ({"post": 10**60}, "post_invalid"),  # would overflow the client token
        ({"decision": "01.06.2026"}, "date_malformed"),
        ({"decision": "2026-02-30"}, "date_malformed"),
        ({"submitted": None, "decision": "2026-06-01"}, "dates_filed_missing"),
        ({"fingerprints": "2026-06-01", "decision": "2026-05-01"}, "dates_order"),
        ({"decision": "2026-01-01"}, "dates_before_filed"),
        ({"submitted": "2014-12-01"}, "dates_before_2015"),
        ({"decision": "2026-11-01"}, "dates_future"),
    ],
)
def test_skip_reasons(change, reason):
    assert pt.map_case(case_dict(**change), TODAY) == reason


def test_ignores_contacts_and_planned_and_reads_float_posts():
    row = pt.map_case(
        case_dict(post=1000.0, contacts=[["2026-01-01", "urge"]], planned=[["x"]]), TODAY
    )
    assert row.key == "1000"
    assert pt.map_case("nope", TODAY) == "malformed"


def test_sample_mapping_and_cases_sharing_a_post():
    rows, skipped = pt.map_cases(sample()["cases"], TODAY)
    assert dict(skipped) == {"basis_other": 5, "dates_filed_missing": 1, "dates_order": 1}
    assert len(rows) == 14
    # Post 204 reports two cases: both kept, the second with an ordinal.
    assert rows["204"].purpose == P.rodzina and rows["204/2"].purpose == P.jdg


# --- importing -------------------------------------------------------------------------


async def run_import(session_factory, data=None, **kw) -> pt.Report:
    async with session_factory() as s:
        report = await pt.import_dataset(s, data or sample(), TODAY, **kw)
        await s.commit()
    return report


async def imported(session_factory) -> dict[str, Case]:
    async with session_factory() as s:
        cases = await repo.list_cases(s, repo.SYSTEM_TG_ID)
    return {pt.key_of(c.client_token): c for c in cases}


async def count(session_factory, model, *where) -> int:
    async with session_factory() as s:
        return await s.scalar(select(func.count()).select_from(model).where(*where))


async def test_first_import(session_factory):
    report = await run_import(session_factory)
    assert (report.new, report.updated, report.unchanged, report.deleted) == (14, 0, 0, 0)
    assert sum(report.skipped.values()) == 7
    cases = await imported(session_factory)
    assert len(cases) == 14
    assert all(c.tg_id == repo.SYSTEM_TG_ID for c in cases.values())
    assert {c.source for c in cases.values()} == {"pobytrack"}
    assert cases["204/2"].client_token == "pobytrack:204/2"
    assert cases["103"].client_token == "pobytrack:103"
    assert cases["103"].voivodeship == "dolnoslaskie" and cases["103"].channel == "mos"
    assert report.recomputed == len({(c.voivodeship, c.purpose) for c in cases.values()})

    # Calendar: one upsert per milestone, with the source line in the description.
    milestones = sum(len(c.milestones) for c in cases.values())
    assert await count(session_factory, OutboxRow, OutboxRow.op == "upsert") == milestones
    async with session_factory() as s:
        row = await s.scalar(select(OutboxRow).where(OutboxRow.case_id == cases["103"].id))
    assert row.payload["title"] == "Dolnośląskie · бизнес (JDG) · подача"
    assert row.payload["description"].endswith(
        "\n\nИсточник: t.me/pobytrack\nАнонимные данные из @czekachiko_bot"
    )


async def test_source_line_is_one_constant(session_factory, monkeypatch):
    monkeypatch.setattr(repo, "IMPORT_SOURCE_LINES", {})
    await run_import(session_factory)
    async with session_factory() as s:
        payloads = (await s.scalars(select(OutboxRow.payload))).all()
    assert payloads and not any("pobytrack" in p["description"] for p in payloads)


async def test_reimport_changes_nothing(session_factory):
    await run_import(session_factory)
    async with session_factory() as s:
        await s.execute(OutboxRow.__table__.delete())  # as if the calendar worker drained it
        await s.commit()
    again = await run_import(session_factory)
    assert (again.new, again.updated, again.deleted, again.unchanged) == (0, 0, 0, 14)
    assert again.changes == 0 and again.recomputed == 0
    assert await count(session_factory, OutboxRow) == 0


def edited(fn) -> dict:
    data = sample()
    for c in data["cases"]:
        fn(c)
    return data


async def test_update_path(session_factory):
    await run_import(session_factory)
    before = await imported(session_factory)

    def change(c):
        if c["post"] == 103:
            c["fingerprints"] = "2026-07-01"  # a new date
            c["method"] = "post"
        if c["post"] == 105:
            c["basis"] = "work"  # bc → praca: a different aggregate key

    report = await run_import(session_factory, edited(change))
    assert (report.new, report.updated, report.deleted, report.unchanged) == (0, 2, 0, 12)
    after = await imported(session_factory)
    assert after["103"].id == before["103"].id and after["103"].channel == "paper"
    assert after["103"].dates()[M.fingerprints] == date(2026, 7, 1)
    assert after["105"].purpose == "praca" and after["105"].id != before["105"].id
    # 103's key, and both the old and new keys of 105.
    assert report.recomputed == 3
    async with session_factory() as s:
        agg = await repo.get_aggregate(s, "dolnoslaskie", "jdg", M.filed, M.fingerprints)
        gone = await s.scalar(select(Case).where(Case.id == before["105"].id))
        deletes = (
            await s.scalars(select(OutboxRow.milestone).where(
                OutboxRow.case_id == before["105"].id, OutboxRow.op == "delete"))
        ).all()  # fmt: skip
    assert (agg.n, agg.min) == (1, (date(2026, 7, 1) - date(2026, 3, 17)).days) and gone is None
    assert sorted(deletes) == sorted(before["105"].dates())


async def test_removed_dates_are_dropped(session_factory):
    await run_import(session_factory)
    target = next(k for k, c in (await imported(session_factory)).items() if len(c.milestones) > 2)
    post = int(target.split("/")[0])

    def change(c):
        if c["post"] == post:
            c["decision"] = c["card"] = None
            c["fingerprints"] = None

    report = await run_import(session_factory, edited(change))
    assert report.updated >= 1
    case = (await imported(session_factory))[target]
    assert set(case.dates()) <= {"filed", "braki"}


async def test_delete_path(session_factory):
    await run_import(session_factory)
    victim = (await imported(session_factory))["105"]  # the only Blue Card case with intervals
    key = (AggregateRow.voivodeship == "dolnoslaskie", AggregateRow.purpose == "blue_card")
    assert await count(session_factory, AggregateRow, *key) > 0
    data = sample()
    data["cases"] = [c for c in data["cases"] if c["post"] != 105]
    report = await run_import(session_factory, data)
    assert (report.deleted, report.new, report.updated) == (1, 0, 0)
    assert "105" not in await imported(session_factory)
    deletes = await count(
        session_factory, OutboxRow, OutboxRow.case_id == victim.id, OutboxRow.op == "delete"
    )
    assert deletes == len(victim.milestones)
    assert await count(session_factory, AggregateRow, *key) == 0


async def test_aggregates_and_stats_include_imported_cases(session_factory):
    async with session_factory() as s:
        before = await repo.get_aggregate(s, None, "praca", M.filed, M.fingerprints)
    assert before is None
    await run_import(session_factory)
    rows, _ = pt.map_cases(sample()["cases"], TODAY)
    expected = sorted(
        (r.dates[M.fingerprints] - r.dates[M.filed]).days
        for r in rows.values()
        if r.purpose == P.praca and M.fingerprints in r.dates
    )
    async with session_factory() as s:
        nat = await repo.get_aggregate(s, None, "praca", M.filed, M.fingerprints)
    assert expected and nat.n == len(expected) and (nat.min, nat.max) == (expected[0], expected[-1])


async def test_one_bad_record_does_not_block_the_import(session_factory):
    data = sample()
    data["cases"].append(case_dict(post=10**60))
    report = await run_import(session_factory, data)
    assert report.new == 14 and report.skipped["post_invalid"] == 1


async def test_shrinking_dataset_is_refused(session_factory):
    await run_import(session_factory)
    data = sample()
    data["cases"] = data["cases"][:3]
    with pytest.raises(pt.DatasetError):
        await run_import(session_factory, data)
    assert len(await imported(session_factory)) == 14
    report = await run_import(session_factory, data, allow_shrink=True)
    assert report.deleted > 0


# --- failures --------------------------------------------------------------------------


async def test_a_failed_import_changes_nothing(session_factory, monkeypatch):
    assert (await pt.sync(session_factory, sample(), TODAY)).new == 14
    snapshot = {k: (c.id, c.dates()) for k, c in (await imported(session_factory)).items()}

    for broken in ({"cases": "nope"}, {"generated": "x", "cases": []}):
        with pytest.raises(pt.DatasetError):
            await pt.sync(session_factory, broken, TODAY)

    # A failure halfway through the upsert rolls the whole import back.
    calls = {"n": 0}
    real = repo.write_dates

    async def flaky(s, case, dates):
        calls["n"] += 1
        if calls["n"] == 5:
            raise RuntimeError("disk full")
        return await real(s, case, dates)

    monkeypatch.setattr(repo, "write_dates", flaky)
    changed = edited(lambda c: c.update(decision=None, card=None))
    with pytest.raises(RuntimeError):
        await pt.sync(session_factory, changed, TODAY)
    after = {k: (c.id, c.dates()) for k, c in (await imported(session_factory)).items()}
    assert after == snapshot


async def test_dry_run_saves_nothing(session_factory):
    report = await pt.sync(session_factory, sample(), TODAY, dry_run=True)
    assert report.new == 14 and await imported(session_factory) == {}


# --- who may see and touch imported cases -----------------------------------------------


async def test_imported_cases_stay_out_of_people_paths(session_factory, api):
    await run_import(session_factory)
    async with session_factory() as s:
        await repo.ensure_user(s, 5)
        await repo.create_case(s, 5, V.mazowieckie, P.jdg, Channel.mos, date(2026, 3, 6), "own")
        await s.commit()
        assert await repo.admin_counts(s) == [("mazowieckie", 1)]
        assert sum(n for _, n in await repo.case_counts(s)) == 15
        assert await repo.source_counts(s) == [("pobytrack", 14), ("user", 1)]
        own = await repo.list_cases(s, 5)
        assert own[0].source == "user"
        assert all(c.tg_id != repo.SYSTEM_TG_ID for c in await repo.admin_recent(s))
    some = next(iter((await imported(session_factory)).values()))
    assert (await api.call("GET", f"/api/cases/{some.id}")).status == 404
    mine = await api.json(
        "POST",
        "/api/cases",
        status=201,
        json={"voivodeship": "mazowieckie", "purpose": "jdg", "channel": "mos",
              "filed": "2026-03-06", "client_token": "tok-source-1"},
    )  # fmt: skip
    detail = await api.json("GET", f"/api/cases/{mine['id']}")
    assert "source" not in mine and "source" not in detail  # internal only
    await api.json("DELETE", f"/api/cases/{mine['id']}", status=204)
    assert await api.json("GET", "/api/cases") == []
    signed = sign_init_data(user={"id": -1, "first_name": "S"}, auth_date=int(api.time.t))
    r = await api.call("GET", "/api/me", signed=False, headers={"Authorization": f"tma {signed}"})
    assert r.status == 401


async def test_admin_lists_imported_apart(session_factory):
    from czekachiko.app import build_dispatcher
    from tests.fakes import make_bot

    await run_import(session_factory)
    bot, tg = make_bot()
    dp = build_dispatcher(session_factory, clock=lambda: TODAY, admin_tg_id=777, throttle=False)
    await dp.feed_update(bot, text_update(777, "/admin"))
    text = tg.last().text
    assert "pobytrack: 14" in text and "#" not in text  # no imported case among recent ones


# --- command line ----------------------------------------------------------------------


def test_cli_dry_run_reads_a_file(db_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("BOT_TOKEN", "42:TEST")
    assert pt.main(["--file", str(FIXTURE), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "new: 14" in out and "basis_other: 5" in out and "dry run" in out
    assert pt.main(["--file", str(FIXTURE.with_suffix(".missing"))]) == 1
    assert "nothing changed" in capsys.readouterr().err


def test_cli_reports_a_failed_fetch(db_url, monkeypatch, capsys):
    async def offline(url=None, client=None):
        raise httpx.ConnectError("offline")

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("BOT_TOKEN", "42:TEST")
    monkeypatch.setattr(pt, "fetch_dataset", offline)
    assert pt.main(["--url", "https://data.example/pobyt.json"]) == 1
    assert "ConnectError" in capsys.readouterr().err


def test_no_scheduled_import():
    from czekachiko.config import Settings

    assert not hasattr(pt, "run_daily") and not hasattr(pt, "start_daily")
    assert "pobytrack_import" not in Settings.model_fields


def test_reports_render():
    report = pt.Report(new=1, skipped=copy.copy(pt.Counter({"basis_other": 2})))
    assert report.lines()[0] == "new: 1" and "  basis_other: 2" in report.lines()


async def test_inline_lists_imported_data_cheaply(session_factory):
    from contextlib import ExitStack

    from aiogram.methods import AnswerInlineQuery
    from aiogram.types import InlineQuery, Update

    from czekachiko.app import build_dispatcher
    from tests.fakes import _ids, _user, make_bot
    from tests.test_permit_stats import count_queries

    await run_import(session_factory)
    bot, tg = make_bot()
    dp = build_dispatcher(session_factory, clock=lambda: TODAY, throttle=False)
    iq = InlineQuery(id=str(next(_ids)), from_user=_user(548), query="", offset="")
    with ExitStack() as stack:
        queries = stack.enter_context(count_queries(session_factory))
        await dp.feed_update(bot, Update(update_id=next(_ids), inline_query=iq))
    (answer,) = [c for c in tg.calls if isinstance(c, AnswerInlineQuery)]
    rows, _ = pt.map_cases(sample()["cases"], TODAY)
    with_intervals = {(r.voivodeship, r.purpose) for r in rows.values() if len(r.dates) > 1}
    assert len(answer.results) == len(with_intervals) == 11  # every key with a chain
    assert {r.id for r in answer.results} >= {"s:jdg:13", "s:studia:1", "s:rodzina:5"}
    assert len(queries) <= 5 * len(answer.results) + 10  # five per card, not per pair tried
