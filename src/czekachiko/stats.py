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

# Where forecast values come from: the case's voivodeship or all of Poland, for its own purpose
# or for every basis of its permit type (the group). With a filing channel, the plain scopes
# are that channel's and `_any` ones cover every channel; without one, only the plain scopes
# are used and they cover every channel.
Scope = Literal[
    "voiv",
    "voiv_group",
    "national",
    "national_group",
    "voiv_any",
    "voiv_group_any",
    "national_any",
    "national_group_any",
]
Lookup = Callable[[Scope, Milestone, Milestone], Sequence[int]]
ScopeLabel = Literal[
    "voiv",
    "voiv_filed",
    "voiv_group",
    "national",
    "national_group",
    "voiv_any",
    "voiv_filed_any",
    "voiv_group_any",
    "national_any",
    "national_group_any",
]


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
    scope: ScopeLabel | None = None
    waited_longer_than: int | None = None
    total: int | None = None
    fastest: int | None = None
    slowest: int | None = None


Attempt = tuple[Scope, ScopeLabel, Milestone]


def plan(
    case_dates: Mapping[Milestone, date], with_group: bool = True, by_channel: bool = False
) -> tuple[Milestone, Milestone, list[Attempt]] | None:
    """Target, anchor and the lookups a forecast tries, most specific first.

    Same voivodeship and purpose (from the latest anchor, then from filing), then the same
    voivodeship and every basis of the permit type, then all of Poland for the purpose, then
    all of Poland for the permit type. `with_group=False` drops the group steps, for permit
    types with a single basis where they would repeat the purpose.

    `by_channel=True` runs those steps for the case's filing channel, then once more over
    every channel (scopes and labels ending in `_any`).
    """
    target = next((m for m in FORECAST_TARGETS if m not in case_dates), None)
    if target is None:
        return None
    before = ANCHORS[: ANCHORS.index(target)] if target in ANCHORS else ANCHORS
    anchor = next(m for m in reversed(before) if m in case_dates)

    def steps(suffix: str) -> list[Attempt]:
        out: list[Attempt] = [(f"voiv{suffix}", f"voiv{suffix}", anchor)]
        if anchor != Milestone.filed:
            out.append((f"voiv{suffix}", f"voiv_filed{suffix}", Milestone.filed))
        if with_group:
            out.append((f"voiv_group{suffix}", f"voiv_group{suffix}", anchor))
        out.append((f"national{suffix}", f"national{suffix}", anchor))
        if with_group:
            out.append((f"national_group{suffix}", f"national_group{suffix}", anchor))
        return out

    attempts = steps("") + (steps("_any") if by_channel else [])
    return target, anchor, attempts


def forecast(
    case_dates: Mapping[Milestone, date],
    today: date,
    lookup: Lookup,
    with_group: bool = True,
    by_channel: bool = False,
) -> Forecast | None:
    planned = plan(case_dates, with_group, by_channel)
    if planned is None:
        return None
    target, anchor, attempts = planned
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
