"""Statistics assembled from the database, shared by the bot screens and the API."""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.db.models import Case
from czekachiko.domain import INTERVAL_PAIRS, Milestone, Purpose, Voivodeship
from czekachiko.stats import (
    WHO_NOW_DAYS,
    Aggregate,
    Forecast,
    aggregate,
    forecast,
    is_suspicious,
    who_now,
)

M = Milestone
Span = tuple[date, date]


async def case_forecast(s: AsyncSession, case: Case, today: date) -> Forecast | None:
    values: dict[tuple[str, M, M], list[int]] = {}
    for scope in ("voiv", "national"):
        for a, b in INTERVAL_PAIRS:
            values[(scope, a, b)] = await repo.interval_values(
                s, scope, case.voivodeship, case.purpose, a, b
            )
    return forecast(case.dates(), today, lambda sc, a, b: values.get((sc, a, b), []))


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
    s: AsyncSession, voiv: Voivodeship, purpose: Purpose, today: date
) -> tuple[Span | None, Span | None]:
    """Filing months now reaching fingerprints and decisions, from the last 30 days."""
    since = today - timedelta(days=WHO_NOW_DAYS)
    fp = who_now(await repo.recent_events(s, voiv, purpose, M.fingerprints, since), today)
    dec = who_now(await repo.recent_events(s, voiv, purpose, M.decision, since), today)
    return fp, dec
