"""Statistics split by filing channel: lookups, stored aggregates and changing a channel.

`unknown` (imported cases whose source does not say) counts only where no channel is asked.
"""

from datetime import date, timedelta

from czekachiko.db import repo
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.forecasting import case_forecast, find_outlier, stats_chain, who_now_spans

C, M, V, P = Channel, Milestone, Voivodeship, Purpose
FILED = date(2026, 1, 5)
TODAY = date(2026, 10, 29)
TODAY_FILED = TODAY - timedelta(days=20)
# (owner, channel, days from filing to fingerprints). Invented.
CASES = [
    (1, C.in_person, 0),
    (2, C.in_person, 0),
    (3, C.post, 120),
    (4, C.post, 140),
    (5, C.mos, 90),
    (repo.SYSTEM_TG_ID, C.unknown, 60),
]


async def seed(s, voiv=V.mazowieckie, purpose=P.jdg):
    cases = []
    for i, (tg, channel, days) in enumerate(CASES):
        dates = {M.filed: FILED, M.fingerprints: FILED + timedelta(days=days)}
        if tg == repo.SYSTEM_TG_ID:
            await repo.ensure_user(s, tg)
            case = await repo.import_case(
                s, f"pobytrack:{i}", voiv, purpose, channel, dates, "pobytrack"
            )
        else:
            await repo.ensure_user(s, tg)
            case = await repo.create_case(s, tg, voiv, purpose, channel, FILED, f"tok-{i}")
            await repo.set_milestone(s, case, M.fingerprints, dates[M.fingerprints])
        cases.append(case)
    await repo.recompute_for(s, voiv, purpose)
    await s.commit()
    return cases


async def test_interval_values_by_channel(session):
    await seed(session)

    async def values(channel, scope="voiv"):
        return sorted(
            await repo.interval_values(
                session, scope, V.mazowieckie, P.jdg, M.filed, M.fingerprints, channel=channel
            )
        )

    assert await values(C.in_person) == [0, 0]
    assert await values(C.post) == [120, 140]
    assert await values(C.mos, "national") == [90]
    assert await values(None) == [0, 0, 60, 90, 120, 140]  # every channel, unknown included


async def test_aggregates_are_stored_per_channel_and_for_all(session):
    await seed(session)
    post = await repo.get_aggregate(
        session, V.mazowieckie, P.jdg, M.filed, M.fingerprints, channel=C.post
    )
    assert (post.n, post.min, post.max) == (2, 120, 140)
    national = await repo.get_aggregate(session, None, P.jdg, M.filed, M.fingerprints, C.in_person)
    assert (national.n, national.max) == (1 + 1, 0)
    everything = await repo.get_aggregate(session, V.mazowieckie, P.jdg, M.filed, M.fingerprints)
    assert everything.n == 6
    # unknown has no rows of its own.
    assert (
        await repo.get_aggregate(session, V.mazowieckie, P.jdg, M.filed, M.fingerprints, C.unknown)
        is None
    )


async def test_chain_aggregates_and_live_chain_by_channel(session):
    await seed(session)
    stored = await repo.chain_aggregates(session, V.mazowieckie, P.jdg, C.mos)
    assert stored[(M.filed, M.fingerprints)].n == 1
    assert stored[(M.filed, M.decision)] is None
    live = await repo.live_chain(session, None, [P.jdg, P.praca], C.post)
    assert live[(M.filed, M.fingerprints)].n == 2
    assert (await repo.live_chain(session, None, [P.jdg]))[(M.filed, M.fingerprints)].n == 6


async def test_recent_events_by_channel(session):
    await seed(session)
    since = FILED - timedelta(days=1)
    post = await repo.recent_events(session, None, P.jdg, M.fingerprints, since, channel=C.post)
    assert len(post) == 2
    assert len(await repo.recent_events(session, None, P.jdg, M.fingerprints, since)) == 6


async def test_chain_keys_count_every_channel(session):
    # Inline cards are channel-agnostic: a key with only unknown cases still has a chain.
    await repo.ensure_user(session, repo.SYSTEM_TG_ID)
    dates = {M.filed: FILED, M.fingerprints: FILED + timedelta(days=50)}
    await repo.import_case(session, "pobytrack:1", V.opolskie, P.praca, C.unknown, dates, "x")
    await repo.recompute_for(session, V.opolskie, P.praca)
    await session.commit()
    assert ("opolskie", "praca") in await repo.chain_keys(session)


async def seed_fingerprints(s, channel, days_list, voiv=V.mazowieckie, start=0):
    for i, days in enumerate(days_list, start):
        await repo.ensure_user(s, 500 + i)
        case = await repo.create_case(s, 500 + i, voiv, P.jdg, channel, FILED, f"fp-{i}")
        await repo.set_milestone(s, case, M.fingerprints, FILED + timedelta(days=days))


async def test_case_forecast_uses_the_case_channel_first(session):
    await seed_fingerprints(session, C.mos, [60, 70, 80, 90, 100])
    await seed_fingerprints(session, C.post, [150, 160], start=5)
    await repo.ensure_user(session, 1)
    mos = await repo.create_case(session, 1, V.mazowieckie, P.jdg, C.mos, TODAY_FILED, "mine")
    post = await repo.create_case(session, 1, V.mazowieckie, P.jdg, C.post, TODAY_FILED, "m2")
    await session.commit()

    f = await case_forecast(session, mos, TODAY)
    assert (f.kind, f.scope, f.fastest, f.slowest) == ("window", "voiv", 60, 100)
    # Two post cases are too few: every channel in the voivodeship, said as such.
    f = await case_forecast(session, post, TODAY)
    assert (f.kind, f.scope, f.n, f.slowest) == ("window", "voiv_any", 7, 160)
    # Inline cards stay channel-agnostic, under the plain names.
    f = await case_forecast(session, post, TODAY, by_channel=False)
    assert (f.scope, f.n) == ("voiv", 7)


async def test_stats_chain_and_who_now_by_channel(session):
    await seed(session)
    chain = await stats_chain(session, V.mazowieckie, (P.jdg,), C.post)
    assert chain[(M.filed, M.fingerprints)].n == 2
    pooled = await stats_chain(session, None, (P.jdg, P.praca), C.in_person)
    assert pooled[(M.filed, M.fingerprints)].n == 2
    assert (await stats_chain(session, None, (P.jdg,)))[(M.filed, M.fingerprints)].n == 6

    # Three in-person cases gave fingerprints on the filing day. Over every channel that is
    # "who is being called now"; in person nobody is called, so there is no span.
    await seed_fingerprints(session, C.in_person, [0, 0, 0], start=20)
    day = FILED + timedelta(days=1)
    assert (await who_now_spans(session, None, P.jdg, day))[0] is not None
    assert (await who_now_spans(session, None, P.jdg, day, C.in_person))[0] is None


async def test_outliers_are_judged_within_the_channel(session):
    # In person, fingerprints on the filing day are the norm, not an outlier.
    await seed_fingerprints(session, C.post, [100, 110, 120, 130, 140, 150, 160, 170])
    await seed_fingerprints(session, C.in_person, [0, 0, 0, 0, 1, 2, 0, 0], start=8)
    await repo.ensure_user(session, 1)
    mine = await repo.create_case(session, 1, V.mazowieckie, P.jdg, C.in_person, FILED, "mine")
    dates = {M.filed: FILED, M.fingerprints: FILED}
    assert await find_outlier(session, mine, dates, M.fingerprints) is None
    mine.channel = C.post
    assert await find_outlier(session, mine, dates, M.fingerprints) is not None


async def test_create_case_writes_fingerprints_at_filing_only_for_a_new_in_person_case(session):
    import pytest

    await repo.ensure_user(session, 1)
    new = await repo.create_case(
        session, 1, V.mazowieckie, P.jdg, C.in_person, FILED, "fp-new", fingerprints_at_filing=True
    )
    assert new.dates() == {M.filed: FILED, M.fingerprints: FILED}
    plain = await repo.create_case(session, 1, V.mazowieckie, P.jdg, C.in_person, FILED, "plain")
    # The same token again, with a later filing date: the existing case is returned as is.
    again = await repo.create_case(
        session, 1, V.mazowieckie, P.jdg, C.in_person, FILED + timedelta(days=9), "plain",
        fingerprints_at_filing=True,
    )  # fmt: skip
    assert again.id == plain.id and again.dates() == {M.filed: FILED}
    with pytest.raises(ValueError):
        await repo.create_case(
            session, 1, V.mazowieckie, P.jdg, C.post, FILED, "fp-post", fingerprints_at_filing=True
        )


async def test_set_channel_moves_the_case_between_channels(session):
    cases = await seed(session)
    post_case = cases[2]
    await repo.set_channel(session, post_case, C.mos)
    await session.commit()
    assert post_case.channel == "mos"
    mos = await repo.get_aggregate(
        session, V.mazowieckie, P.jdg, M.filed, M.fingerprints, channel=C.mos
    )
    post = await repo.get_aggregate(
        session, V.mazowieckie, P.jdg, M.filed, M.fingerprints, channel=C.post
    )
    assert (mos.n, post.n) == (2, 1)
    # A key that loses its last case of a channel loses the row.
    await repo.set_channel(session, cases[4], C.post)
    await repo.set_channel(session, post_case, C.post)
    await session.commit()
    assert (
        await repo.get_aggregate(session, V.mazowieckie, P.jdg, M.filed, M.fingerprints, C.mos)
        is None
    )
