"""Zero days from filing that cannot happen are typos: statistics leave them out.

A case number, a call or (filed by post, e-Doręczenia or MOS) fingerprints on the filing day
itself is a data-entry error. In person, fingerprints at the counter are real and count. The
stored dates stay as they are.
"""

from datetime import date, timedelta

from czekachiko.db import repo
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship, zero_day_possible
from czekachiko.forecasting import find_outlier, stats_chain, who_now_spans

C, M, V, P = Channel, Milestone, Voivodeship, Purpose
F = date(2026, 1, 5)
# (owner, channel, {milestone: days from filing}). Invented.
CASES = [
    (1, C.post, {M.case_number: 0, M.braki: 0, M.fingerprints: 0, M.decision: 200}),
    (2, C.post, {M.case_number: 30, M.braki: 40, M.fingerprints: 100}),
    (3, C.in_person, {M.fingerprints: 0, M.case_number: 0}),
    (4, C.mos, {M.fingerprints: 0, M.case_number: 20}),
    (repo.SYSTEM_TG_ID, C.unknown, {M.fingerprints: 0}),
]


async def seed(s):
    cases = []
    for i, (tg, channel, days) in enumerate(CASES):
        dates = {M.filed: F, **{m: F + timedelta(days=d) for m, d in days.items()}}
        await repo.ensure_user(s, tg)
        if tg == repo.SYSTEM_TG_ID:
            case = await repo.import_case(
                s, f"pobytrack:{i}", V.mazowieckie, P.jdg, channel, dates, "pobytrack"
            )
        else:
            case = await repo.create_case(s, tg, V.mazowieckie, P.jdg, channel, F, f"tok-{i}")
            for m, d in dates.items():
                if m != M.filed:
                    await repo.set_milestone(s, case, m, d)
        cases.append(case)
    await repo.recompute_for(s, V.mazowieckie, P.jdg)
    await s.commit()
    return cases


def test_which_zero_days_are_possible():
    assert not zero_day_possible(M.case_number, C.in_person)
    assert not zero_day_possible(M.braki, C.in_person)
    assert zero_day_possible(M.fingerprints, C.in_person)
    for channel in (C.post, C.mos, C.unknown):
        assert not zero_day_possible(M.fingerprints, channel)
    # Only these three: other milestones are not judged.
    assert zero_day_possible(M.decision, C.post)


async def test_interval_values_leave_impossible_zeros_out(session):
    await seed(session)

    async def values(to_m, channel=None, scope="voiv"):
        return sorted(
            await repo.interval_values(
                session, scope, V.mazowieckie, P.jdg, M.filed, to_m, channel=channel
            )
        )

    assert await values(M.case_number, C.post) == [30]
    assert await values(M.braki, C.post) == [40]
    assert await values(M.fingerprints, C.post) == [100]
    assert await values(M.fingerprints, C.in_person) == [0]  # at the counter: real
    assert await values(M.fingerprints, C.mos) == []
    assert await values(M.case_number, C.in_person) == []
    # Every channel: the same rule per case, so in-person zeros stay and the rest go.
    assert await values(M.fingerprints) == [0, 100]
    assert await values(M.fingerprints, scope="national") == [0, 100]
    assert await values(M.case_number) == [20, 30]
    # The typo case's other intervals still count.
    assert await values(M.decision, C.post) == [200]


async def test_stored_aggregates_leave_impossible_zeros_out(session):
    await seed(session)

    async def agg(to_m, channel=None, voiv=V.mazowieckie):
        return await repo.get_aggregate(session, voiv, P.jdg, M.filed, to_m, channel)

    post = await agg(M.fingerprints, C.post)
    assert (post.n, post.min, post.max) == (1, 100, 100)
    assert await agg(M.fingerprints, C.mos) is None  # its only value was a typo
    assert (await agg(M.fingerprints, C.in_person)).n == 1
    everything = await agg(M.fingerprints)
    assert (everything.n, everything.min, everything.max) == (2, 0, 100)
    national = await agg(M.fingerprints, voiv=None)
    assert (national.n, national.min) == (2, 0)
    numbers = await agg(M.case_number)
    assert (numbers.n, numbers.min, numbers.max) == (2, 20, 30)
    assert (await agg(M.braki)).n == 1


async def test_live_chain_and_stats_chain_leave_impossible_zeros_out(session):
    await seed(session)
    live = await repo.live_chain(session, None, [P.jdg, P.praca])
    assert live[(M.filed, M.fingerprints)].n == 2
    assert live[(M.filed, M.case_number)].min == 20
    post = await repo.live_chain(session, V.mazowieckie, [P.jdg, P.praca], C.post)
    assert post[(M.filed, M.braki)].n == 1
    chain = await stats_chain(session, V.mazowieckie, (P.jdg,), C.mos)
    assert chain[(M.filed, M.fingerprints)] is None


async def test_who_now_leaves_impossible_zeros_out(session):
    await seed(session)
    since = F - timedelta(days=1)
    events = await repo.recent_events(session, None, P.jdg, M.fingerprints, since)
    assert sorted(ev - filed for ev, filed in events) == [timedelta(0), timedelta(100)]
    assert await repo.recent_events(session, None, P.jdg, M.fingerprints, since, C.mos) == []
    # Three more MOS "fingerprints on the filing day" are typos: nobody is being called.
    for i in range(3):
        await repo.ensure_user(session, 40 + i)
        case = await repo.create_case(session, 40 + i, V.opolskie, P.jdg, C.mos, F, f"z-{i}")
        await repo.set_milestone(session, case, M.fingerprints, F)
    assert (await who_now_spans(session, V.opolskie, P.jdg, F + timedelta(days=1)))[0] is None


async def test_outlier_check_ignores_impossible_zeros(session):
    # Eight MOS typos at 0 days would make a real 150 look far out; without them there is
    # too little data to judge.
    for i in range(8):
        await repo.ensure_user(session, 60 + i)
        case = await repo.create_case(session, 60 + i, V.mazowieckie, P.jdg, C.mos, F, f"o-{i}")
        await repo.set_milestone(session, case, M.fingerprints, F)
    await repo.ensure_user(session, 1)
    mine = await repo.create_case(session, 1, V.mazowieckie, P.jdg, C.mos, F, "mine")
    dates = {M.filed: F, M.fingerprints: F + timedelta(days=150)}
    assert await find_outlier(session, mine, dates, M.fingerprints) is None


async def test_stored_dates_are_untouched(session):
    cases = await seed(session)
    await repo.recompute_all(session)
    await session.commit()
    for case in cases:
        await session.refresh(case, ["milestones"])
    assert cases[0].dates()[M.case_number] == F
    assert cases[3].dates()[M.fingerprints] == F
