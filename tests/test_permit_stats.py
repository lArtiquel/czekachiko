"""Stats, forecasts and inline cards across permit-type groups and all of Poland."""

from contextlib import contextmanager
from datetime import date, timedelta
from itertools import combinations

from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, Update
from sqlalchemy import event

from czekachiko import cards, share
from czekachiko.app import build_dispatcher
from czekachiko.db import repo
from czekachiko.domain import PERMIT_GROUPS, Channel, Milestone, PermitType, Purpose, Voivodeship
from czekachiko.forecasting import case_forecast, stats_chain, who_now_spans
from czekachiko.stats import forecast
from tests.fakes import _ids, _user, make_bot

M, P, V = Milestone, Purpose, Voivodeship
TODAY = date(2026, 10, 29)
FIVE = [100, 120, 140, 160, 180]


def lookup_from(table):
    return lambda scope, a, b: table.get((scope, a, b), [])


# --- pure forecast -----------------------------------------------------------------------


def test_forecast_tries_the_group_before_all_of_poland():
    case = {M.filed: TODAY - timedelta(days=30)}
    table = {
        ("voiv", M.filed, M.fingerprints): [100, 120],
        ("voiv_group", M.filed, M.fingerprints): FIVE,
        ("national", M.filed, M.fingerprints): FIVE + [200],
    }
    f = forecast(case, TODAY, lookup_from(table))
    assert (f.kind, f.scope, f.n) == ("window", "voiv_group", 5)


def test_forecast_order_ends_with_national_group():
    case = {M.filed: TODAY - timedelta(days=30)}
    f = forecast(case, TODAY, lookup_from({("national_group", M.filed, M.fingerprints): FIVE}))
    assert (f.kind, f.scope) == ("window", "national_group")
    nat = {
        ("national", M.filed, M.fingerprints): FIVE,
        **{("national_group", M.filed, M.fingerprints): FIVE * 2},
    }
    assert forecast(case, TODAY, lookup_from(nat)).scope == "national"


def test_forecast_without_group_skips_group_steps():
    case = {M.filed: TODAY - timedelta(days=30)}
    table = {("voiv_group", M.filed, M.fingerprints): FIVE}
    assert forecast(case, TODAY, lookup_from(table), with_group=False).kind == "no_data"


def test_waited_longer_still_stops_at_the_first_group_with_enough_cases():
    case = {M.filed: TODAY - timedelta(days=500)}
    table = {
        ("voiv_group", M.filed, M.fingerprints): FIVE,
        ("national", M.filed, M.fingerprints): [600] * 5,
    }
    f = forecast(case, TODAY, lookup_from(table))
    assert (f.kind, f.scope, f.waited_longer_than, f.total) == ("waited_longer", "voiv_group", 5, 5)


# --- with the database -------------------------------------------------------------------


@contextmanager
def count_queries(session_factory):
    engine = session_factory.kw["bind"].sync_engine
    seen: list[str] = []

    def before(conn, cursor, statement, *args):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", before)


async def seed(session_factory, rows, uid=4000):
    """rows: (voivodeship, purpose, filed, fingerprints or None)."""
    ids = []
    async with session_factory() as s:
        for i, (voiv, purpose, filed, fp) in enumerate(rows):
            await repo.ensure_user(s, uid + i)
            c = await repo.create_case(
                s, uid + i, voiv, purpose, Channel.mos, filed, f"ps{uid + i}"
            )
            if fp is not None:
                await repo.set_milestone(s, c, M.fingerprints, fp)
            ids.append(c.id)
        await s.commit()
    return ids


async def test_case_forecast_uses_the_voivodeship_group(session_factory):
    filed = date(2026, 1, 1)
    spans = [(P.jdg, 150), (P.praca, 160), (P.studia, 170), (P.rodzina, 180), (P.inne, 190)]
    others = [(V.mazowieckie, p, filed, filed + timedelta(days=d)) for p, d in spans]
    nationals = [(V.slaskie, P.blue_card, filed, filed + timedelta(days=90 + i)) for i in range(5)]
    (mine, *_) = await seed(
        session_factory, [(V.mazowieckie, P.blue_card, date(2026, 6, 1), None), *others, *nationals]
    )
    async with session_factory() as s:
        case = await repo.get_case(s, 4000, mine)
        with count_queries(session_factory) as queries:
            f = await case_forecast(s, case, TODAY)
    assert (f.kind, f.scope, f.n) == ("window", "voiv_group", 5)
    # Prefetches only what the plan can try: voiv, voiv_group, national, national_group.
    assert len(queries) == 4
    text = cards.forecast_text("ru", case, f)
    assert "Mazowieckie, временный побыт, все основания" in text and "«Blue Card»" in text


async def test_single_basis_types_skip_the_group(session_factory):
    filed = date(2026, 1, 1)
    rows = [(V.slaskie, P.staly, filed, filed + timedelta(days=200 + i)) for i in range(5)]
    (mine, *_) = await seed(
        session_factory, [(V.mazowieckie, P.staly, date(2026, 6, 1), None), *rows]
    )
    async with session_factory() as s:
        case = await repo.get_case(s, 4000, mine)
        with count_queries(session_factory) as queries:
            f = await case_forecast(s, case, TODAY)
    assert (f.kind, f.scope) == ("window", "national")
    assert len(queries) == 2  # voiv, national: no group lookups for a one-basis type
    assert "вся Польша, постоянный побыт" in cards.forecast_text("ru", case, f)


async def test_stats_paths_query_counts(session_factory):
    filed = date(2026, 1, 1)
    await seed(
        session_factory,
        [
            (V.mazowieckie, p, filed, filed + timedelta(days=100))
            for p in PERMIT_GROUPS[PermitType.temporary]
        ],
    )
    temporary = PERMIT_GROUPS[PermitType.temporary]
    async with session_factory() as s:
        for voiv, purposes, expected in [
            (V.mazowieckie, (P.praca,), 5),  # aggregates table, five rows
            (None, (P.praca,), 5),  # national rows of the same table
            (V.mazowieckie, temporary, 1),  # one interval query for the whole chain
            (None, (P.praca, P.jdg), 1),
        ]:
            with count_queries(session_factory) as queries:
                chain = await stats_chain(s, voiv, purposes)
            assert len(queries) == expected, (voiv, purposes)
            assert chain[(M.filed, M.fingerprints)].n == len(purposes)
            with count_queries(session_factory) as queries:
                await who_now_spans(s, voiv, purposes, TODAY)
            assert len(queries) == 2


async def test_who_now_for_a_group_and_all_of_poland(session_factory):
    rows = [
        (V.mazowieckie, P.praca, date(2026, 3, 2), date(2026, 10, 10)),
        (V.mazowieckie, P.jdg, date(2026, 4, 6), date(2026, 10, 12)),
        (V.slaskie, P.studia, date(2026, 2, 2), date(2026, 10, 14)),
    ]
    await seed(session_factory, rows)
    group = PERMIT_GROUPS[PermitType.temporary]
    async with session_factory() as s:
        assert (await who_now_spans(s, V.mazowieckie, group, TODAY))[0] is None  # two events
        fp, dec = await who_now_spans(s, None, group, TODAY)
    assert fp == (date(2026, 2, 1), date(2026, 4, 1)) and dec is None


# --- inline cards and codes --------------------------------------------------------------


def test_every_share_code_fits_a_result_id():
    """Telegram caps inline result ids at 64 bytes; the id is the code."""
    worst = [None, *list(V)[-5:]]
    for ps in PERMIT_GROUPS.values():
        for k in range(1, len(ps) + 1):
            for chosen in combinations(ps, k):
                code = share.encode(chosen, worst)
                assert len(code.encode()) <= 64, code
                assert share.decode(code) == (share.selector(chosen), worst)


def test_selection_labels():
    assert cards.selection_label("ru", ["jdg"]) == "бизнес (JDG)"
    assert cards.selection_label("ru", PERMIT_GROUPS[PermitType.temporary]) == (
        "временный побыт, все основания"
    )
    assert cards.selection_label("en", ["jdg", "praca"]) == "work, business (JDG)"
    assert cards.selection_label("en", ["staly"]) == "permanent residence"


async def inline_answer(session_factory, query, uid=548):
    bot, tg = make_bot()
    dp = build_dispatcher(session_factory, clock=lambda: TODAY, throttle=False)
    iq = InlineQuery(id=str(next(_ids)), from_user=_user(uid), query=query, offset="")
    await dp.feed_update(bot, Update(update_id=next(_ids), inline_query=iq))
    (answer,) = [c for c in tg.calls if isinstance(c, AnswerInlineQuery)]
    return answer


async def test_inline_cards_for_groups_and_all_of_poland(session_factory):
    filed = date(2026, 1, 1)
    await seed(
        session_factory,
        [
            (V.mazowieckie, P.praca, filed, filed + timedelta(days=100)),
            (V.mazowieckie, P.blue_card, filed, filed + timedelta(days=60)),
            (V.slaskie, P.jdg, filed, filed + timedelta(days=200)),
        ],
    )
    answer = await inline_answer(session_factory, "s:temporary:6,all")
    (result,) = answer.results
    assert result.id == "s:temporary:6,all"
    assert result.title == "Mazowieckie, Вся Польша · временный побыт, все основания"
    text = result.input_message_content.message_text
    assert text.startswith(
        "📊 <b>Czekachiko · временный побыт, все основания</b>\n\n<b>Mazowieckie</b>"
    )
    assert "в среднем 80 дн. (мин 60, макс 100) (дел: 2)" in text
    assert "<b>Вся Польша</b>" in text and "в среднем 120 дн. (мин 60, макс 200) (дел: 3)" in text

    answer = await inline_answer(session_factory, "s:jdg+praca:all")
    assert answer.results[0].title == "Вся Польша · работа, бизнес (JDG)"
    assert share.decode("s:praca+staly:6") is None  # bases of two permit types


async def test_inline_search_finds_new_bases(session_factory):
    filed = date(2026, 1, 1)
    await seed(
        session_factory, [(V.mazowieckie, P.rezydent_ue, filed, filed + timedelta(days=250))]
    )
    answer = await inline_answer(session_factory, "резидент варшава")
    assert [r.id for r in answer.results] == ["s:rezydent_ue:6"]
    assert answer.results[0].title == "Mazowieckie · резидент ЕС"
