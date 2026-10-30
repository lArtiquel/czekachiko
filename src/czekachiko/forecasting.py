"""Statistics assembled from the database, shared by the bot screens and the API."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.db.models import Case
from czekachiko.domain import (
    INTERVAL_PAIRS,
    PERMIT_GROUPS,
    PERMIT_TYPE,
    USER_CHANNELS,
    Channel,
    Milestone,
    Purpose,
    Voivodeship,
    channel_path,
)
from czekachiko.stats import (
    WHO_NOW_DAYS,
    Aggregate,
    Forecast,
    aggregate,
    forecast,
    is_suspicious,
    plan,
    who_now,
)

M = Milestone
Span = tuple[date, date]
Chain = dict[tuple[M, M], Aggregate | None]


def group_bases(purpose: Purpose | str) -> tuple[Purpose, ...]:
    """Every basis of the purpose's permit type; empty for an unknown purpose."""
    permit_type = PERMIT_TYPE.get(purpose)
    return PERMIT_GROUPS[permit_type] if permit_type is not None else ()


def case_channel(case: Case) -> Channel | None:
    """The channel the case's statistics are split by; None (every channel) for unknown."""
    return Channel(case.channel) if case.channel in USER_CHANNELS else None


async def case_forecast(
    s: AsyncSession, case: Case, today: date, by_channel: bool = True
) -> Forecast | None:
    """`by_channel=False` is the channel-agnostic forecast of inline cards."""
    channel = case_channel(case) if by_channel else None
    group = group_bases(case.purpose)
    with_group = len(group) > 1
    planned = plan(case.dates(), with_group, by_channel=channel is not None)
    if planned is None:
        return None
    target, _, attempts = planned
    values: dict[tuple[str, M, M], list[int]] = {}

    def run() -> Forecast | None:
        return forecast(
            case.dates(),
            today,
            lambda sc, a, b: values.get((sc, a, b), []),
            with_group=with_group,
            by_channel=channel is not None,
        )

    # Only the lookups the forecast can try, in two rounds: the channel's (at most five
    # queries), then every channel's only when those had too little data.
    for every_channel in (False, True):
        for scope, _, k in attempts:
            if scope.endswith("_any") != every_channel:
                continue
            purposes = group if "_group" in scope else case.purpose
            where = "national" if scope.startswith("national") else "voiv"
            values[(scope, k, target)] = await repo.interval_values(
                s,
                where,
                case.voivodeship,
                purposes,
                k,
                target,
                channel=None if every_channel else channel,
            )
        result = run()
        if result.kind != "no_data" or channel is None:
            return result
    return result


async def stats_chain(
    s: AsyncSession,
    voiv: Voivodeship | str | None,
    purposes: tuple[Purpose, ...],
    channel: Channel | None = None,
) -> Chain:
    """The chain for a voivodeship (None: all of Poland), one or more purposes and a channel
    (None: every channel).

    One purpose reads the aggregates table (five indexed lookups); a set of purposes is
    computed from intervals in a single query, since medians cannot be added up.
    """
    if len(purposes) == 1:
        return await repo.chain_aggregates(s, voiv, purposes[0], channel)
    return await repo.live_chain(s, voiv, purposes, channel)


async def find_outlier(
    s: AsyncSession, case: Case, dates: dict[M, date], milestone: M
) -> tuple[M, M, int, Aggregate] | None:
    """The first interval touching `milestone` that is far outside the spread of cases filed
    the same way in its voivodeship."""
    channel = case_channel(case)
    for a, b in INTERVAL_PAIRS:
        if milestone not in (a, b) or a not in dates or b not in dates:
            continue
        value = (dates[b] - dates[a]).days
        values = await repo.interval_values(
            s, "voiv", case.voivodeship, case.purpose, a, b, channel=channel
        )
        if is_suspicious(value, values):
            return a, b, value, aggregate(values)
    return None


def fingerprints_at_filing(channel: Channel | None) -> bool:
    return channel is not None and any(
        st.at_filing for st in channel_path(channel) if st.milestone == M.fingerprints
    )


async def who_now_spans(
    s: AsyncSession,
    voiv: Voivodeship | None,
    purpose: repo.PurposeSet,
    today: date,
    channel: Channel | None = None,
) -> tuple[Span | None, Span | None]:
    """Filing months now reaching fingerprints and decisions, from the last 30 days.

    `voiv=None` means all of Poland; `purpose` may be one purpose or several. Where a channel
    gives fingerprints at filing, nobody is called for them, so that span is None.
    """
    since = today - timedelta(days=WHO_NOW_DAYS)
    fp = None
    if not fingerprints_at_filing(channel):
        events = await repo.recent_events(s, voiv, purpose, M.fingerprints, since, channel)
        fp = who_now(events, today)
    dec = who_now(await repo.recent_events(s, voiv, purpose, M.decision, since, channel), today)
    return fp, dec
