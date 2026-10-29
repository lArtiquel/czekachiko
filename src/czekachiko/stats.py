"""Pure statistics: aggregates, outlier detection, forecasts. No I/O."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from czekachiko.domain import ANCHORS, FORECAST_TARGETS, Milestone

MIN_WINDOW_N = 5
MIN_OUTLIER_N = 8
WHO_NOW_DAYS = 30
WHO_NOW_MIN = 3

Scope = Literal["voiv", "national"]
Lookup = Callable[[Scope, Milestone, Milestone], Sequence[int]]


def percentile(values: Sequence[int], q: float) -> float:
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


@dataclass(frozen=True)
class Aggregate:
    n: int
    p10: float
    median: float
    p90: float
    min: int
    max: int
    mean: float


def aggregate(values: Sequence[int]) -> Aggregate | None:
    if not values:
        return None
    return Aggregate(
        n=len(values),
        p10=percentile(values, 0.1),
        median=percentile(values, 0.5),
        p90=percentile(values, 0.9),
        min=min(values),
        max=max(values),
        mean=sum(values) / len(values),
    )


def is_suspicious(value: int, values: Sequence[int]) -> bool:
    """Far outside the group's usual spread; only judged once the group has 8+ values."""
    if len(values) < MIN_OUTLIER_N:
        return False
    q1, q3 = percentile(values, 0.25), percentile(values, 0.75)
    # Floor the IQR so a group of identical values does not flag every neighbour.
    iqr = max(q3 - q1, 0.1 * percentile(values, 0.5), 7)
    return value < q1 - 3 * iqr or value > q3 + 3 * iqr


@dataclass(frozen=True)
class Forecast:
    kind: Literal["window", "waited_longer", "no_data"]
    anchor: Milestone
    target: Milestone
    start: date | None = None
    likely: date | None = None
    end: date | None = None
    n: int = 0
    scope: Literal["voiv", "voiv_filed", "national"] | None = None
    waited_longer_than: int | None = None
    total: int | None = None
    fastest: int | None = None
    slowest: int | None = None


def forecast(case_dates: Mapping[Milestone, date], today: date, lookup: Lookup) -> Forecast | None:
    target = next((m for m in FORECAST_TARGETS if m not in case_dates), None)
    if target is None:
        return None
    before = ANCHORS[: ANCHORS.index(target)] if target in ANCHORS else ANCHORS
    anchor = next(m for m in reversed(before) if m in case_dates)
    attempts = [("voiv", "voiv", anchor), ("national", "national", anchor)]
    if anchor != Milestone.filed:
        attempts.insert(1, ("voiv", "voiv_filed", Milestone.filed))
    for scope, label, k in attempts:
        values = lookup(scope, k, target)
        if len(values) < MIN_WINDOW_N:
            continue
        d = case_dates[k]
        elapsed = (today - d).days
        pool = [v for v in values if v >= elapsed]
        common = dict(
            anchor=k, target=target, scope=label, fastest=min(values), slowest=max(values)
        )
        if len(pool) >= MIN_WINDOW_N:
            return Forecast(
                kind="window",
                start=d + timedelta(days=round(percentile(pool, 0.1))),
                likely=d + timedelta(days=round(percentile(pool, 0.5))),
                end=d + timedelta(days=round(percentile(pool, 0.9))),
                n=len(pool),
                **common,
            )
        return Forecast(
            kind="waited_longer",
            n=len(values),
            waited_longer_than=len(values) - len(pool),
            total=len(values),
            **common,
        )
    return Forecast(kind="no_data", anchor=anchor, target=target)


def who_now(events: Sequence[tuple[date, date]], today: date) -> tuple[date, date] | None:
    """Filing-month span of cases whose milestone happened in the last 30 days."""
    since = today - timedelta(days=WHO_NOW_DAYS)
    filed = [f.replace(day=1) for ev, f in events if since <= ev <= today]
    if len(filed) < WHO_NOW_MIN:
        return None
    return min(filed), max(filed)
