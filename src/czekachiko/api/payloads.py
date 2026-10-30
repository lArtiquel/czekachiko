"""JSON shapes of the API and parsing of its inputs. Pure."""

import re
from collections.abc import Mapping
from datetime import date
from enum import StrEnum

from czekachiko import documents
from czekachiko.dates import parse_date
from czekachiko.domain import (
    PERMIT_GROUPS,
    PERMIT_TYPE,
    USER_CHANNELS,
    Channel,
    Milestone,
    PermitType,
    Purpose,
    canonical,
    channel_path,
)
from czekachiko.stats import Aggregate, Forecast

M = Milestone
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLIENT_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def parse_day(value, today: date) -> date | None:
    """A YYYY-MM-DD string through dates.parse_date; None for anything else."""
    if not isinstance(value, str) or not _ISO_DAY.match(value):
        return None
    return parse_date(value, today)


def parse_enum[E: StrEnum](enum: type[E], value) -> E | None:
    if not isinstance(value, str):
        return None
    try:
        return enum(value)
    except ValueError:
        return None


def parse_channel(value) -> Channel | None:
    """One of the channels people pick; `unknown` belongs to imported cases only."""
    channel = parse_enum(Channel, value)
    return channel if channel in USER_CHANNELS else None


def parse_purposes(query: Mapping[str, str]) -> tuple[tuple[Purpose, ...] | None, dict[str, str]]:
    """`purpose=a,b` (one or more bases of one permit type) or `group=<permit type>`.

    Returns the purposes in picker order, or None and the field errors.
    """
    raw_purpose, raw_group = query.get("purpose"), query.get("group")
    if raw_purpose is not None and raw_group is not None:
        return None, {"group": "exclusive"}
    if raw_group is not None:
        group = parse_enum(PermitType, raw_group)
        return (PERMIT_GROUPS[group], {}) if group else (None, {"group": "invalid"})
    purposes = [parse_enum(Purpose, p) for p in (raw_purpose or "").split(",")]
    if None in purposes:
        return None, {"purpose": "invalid"}
    if len({PERMIT_TYPE[p] for p in purposes}) > 1:
        return None, {"purpose": "mixed"}
    return canonical(purposes), {}


def iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def case_dates(case) -> dict[str, str]:
    dates = case.dates()
    return {m.value: dates[m].isoformat() for m in M if m in dates}


def case_json(case, docs: list) -> dict:
    done, total = documents.progress(case.purpose, docs)
    return {
        "id": case.id,
        "voivodeship": case.voivodeship,
        "purpose": case.purpose,
        "channel": case.channel,
        "dates": case_dates(case),
        "docs_done": done,
        "docs_total": total,
    }


def agg_json(agg: Aggregate | None) -> dict | None:
    if agg is None:
        return None
    # Whole days, like the mean; `mean` stays for clients that read it.
    return {
        "n": agg.n,
        "mean": round(agg.mean),
        "median": round(agg.median),
        "min": agg.min,
        "max": agg.max,
    }


def chain_json(
    chain: dict[tuple[M, M], Aggregate | None],
    dates: dict | None = None,
    channel: Channel | str | None = None,
) -> list:
    """Each milestone from filing, in the channel's path order (no channel: the milestone
    order): the case's own days (if any) and the typical span."""
    dates = dates or {}
    filed = dates.get(M.filed)
    steps = [st.milestone for st in channel_path(channel or Channel.post)][1:]
    return [
        {
            "milestone": b.value,
            "own_days": (dates[b] - filed).days if filed is not None and b in dates else None,
            "agg": agg_json(chain.get((M.filed, b))),
        }
        for b in steps
    ]


def forecast_json(f: Forecast | None) -> dict | None:
    if f is None:
        return None
    return {
        "kind": f.kind,
        "target": f.target.value,
        "start": iso(f.start),
        "likely": iso(f.likely),
        "end": iso(f.end),
        "n": f.n,
        "scope": f.scope,
        "waited_longer_than": f.waited_longer_than,
        "total": f.total,
        "fastest": f.fastest,
        "slowest": f.slowest,
    }


def documents_json(case, docs: list) -> list:
    """The purpose's list first, then the owner's own documents (free text, unescaped)."""
    std = {d.code: d.submitted_on for d in docs if d.code is not None}
    items = [
        {
            "id": None,
            "code": code,
            "name": documents.doc_name(code),
            "date": iso(std.get(code)),
            "custom": False,
        }
        for code in documents.checklist(case.purpose)
    ]
    items += [
        {"id": d.id, "code": None, "name": d.name, "date": iso(d.submitted_on), "custom": True}
        for d in docs
        if d.name is not None
    ]
    return items


def span_json(span: tuple[date, date] | None) -> list[str] | None:
    return [span[0].isoformat(), span[1].isoformat()] if span else None
