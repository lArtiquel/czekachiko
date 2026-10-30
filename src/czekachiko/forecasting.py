"""Statistics assembled from the database, shared by the bot screens and the API."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.db.models import Case
from czekachiko.domain import (
    INTERVAL_PAIRS,
    PERMIT_GROUPS,
    PERMIT_TYPE,
    Milestone,
    Purpose,
    Voivodeship,
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


async def case_forecast(s: AsyncSession, case: Case, today: date) -> Forecast | None:
    group = group_bases(case.purpose)
    with_group = len(group) > 1
    planned = plan(case.dates(), with_group)
    if planned is None:
        return None
    target, _, attempts = planned
    # Only the lookups the forecast can try: at most five queries.
    values: dict[tuple[str, M, M], list[int]] = {}
    for scope, _, k in attempts:
        purposes = group if scope.endswith("_group") else case.purpose
        where = "national" if scope.startswith("national") else "voiv"
        values[(scope, k, target)] = await repo.interval_values(
            s, where, case.voivodeship, purposes, k, target
        )
    return forecast(
        case.dates(), today, lambda sc, a, b: values.get((sc, a, b), []), with_group=with_group
    )


async def stats_chain(
    s: AsyncSession, voiv: Voivodeship | str | None, purposes: tuple[Purpose, ...]
) -> Chain:
    """The chain for a voivodeship (None: all of Poland) and one or more purposes.

    One purpose reads the aggregates table (five indexed lookups); a set of purposes is
    computed from intervals in a single query, since medians cannot be added up.
    """
    if len(purposes) == 1:
        return await repo.chain_aggregates(s, voiv, purposes[0])
    return await repo.live_chain(s, voiv, purposes)


async def find_outlier(
    s: AsyncSession, case: Case, dates: dict[M, date], milestone: M
) -> tuple[M, M, int, Aggregate] | None:
    """The first interval touching `milestone` that is far outside its voivodeship's spread."""
    for a, b in INTERVAL_PAIRS:
        if milestone not in (a, b) or a not in dates or b not in dates:
            continue
        value = (dates[b] - dates[a]).days
        values = await repo.interval_values(s, "voiv", case.voivodeship, case.purpose, a, b)
        if is_suspicious(value, values):
            return a, b, value, aggregate(values)
    return None


async def who_now_spans(
    s: AsyncSession, voiv: Voivodeship | None, purpose: repo.PurposeSet, today: date
) -> tuple[Span | None, Span | None]:
    """Filing months now reaching fingerprints and decisions, from the last 30 days.

    `voiv=None` means all of Poland; `purpose` may be one purpose or several.
    """
    since = today - timedelta(days=WHO_NOW_DAYS)
    fp = who_now(await repo.recent_events(s, voiv, purpose, M.fingerprints, since), today)
    dec = who_now(await repo.recent_events(s, voiv, purpose, M.decision, since), today)
    return fp, dec
