"""Data access. Functions flush but never commit: the caller owns the transaction."""

from collections.abc import Iterable
from datetime import date
from typing import Literal

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko import documents
from czekachiko.db.models import (
    AggregateRow,
    CalendarEvent,
    CalendarRow,
    Case,
    CaseDocument,
    Feedback,
    FeedbackRate,
    MilestoneRow,
    OutboxRow,
    User,
)
from czekachiko.domain import CHAIN, INTERVAL_PAIRS, Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales.ru import MILESTONE_LABELS, PURPOSE_LABELS, VOIV_LABELS
from czekachiko.stats import Aggregate, aggregate

MAX_CASES = 5
# Owns cases imported from community datasets. Telegram user ids are positive and the API
# rejects anything else, so no request can act as this user.
SYSTEM_TG_ID = -1
# Added to calendar descriptions of imported cases; set to None to drop it.
IMPORT_SOURCE_LINE: str | None = "Источник: t.me/pobytrack"


class TooManyCases(Exception):
    pass


class TokenConflict(Exception):
    """A client token already belongs to another user's case."""


# --- users ---------------------------------------------------------------


async def ensure_user(s: AsyncSession, tg_id: int) -> User:
    await s.execute(insert(User).values(tg_id=tg_id).on_conflict_do_nothing())
    return await s.get(User, tg_id)


async def set_lang(s: AsyncSession, tg_id: int, lang: str) -> None:
    (await ensure_user(s, tg_id)).lang = lang
    await s.flush()


async def delete_user(s: AsyncSession, tg_id: int) -> None:
    # By purpose, so aggregate locks are taken in the same order as the importer takes them.
    for case in sorted(await list_cases(s, tg_id), key=lambda c: (c.purpose, c.id)):
        await delete_case(s, case)
    await s.execute(delete(User).where(User.tg_id == tg_id))
    await s.flush()


# --- cases ---------------------------------------------------------------


async def count_cases(s: AsyncSession, tg_id: int) -> int:
    return await s.scalar(select(func.count()).select_from(Case).where(Case.tg_id == tg_id))


async def list_cases(s: AsyncSession, tg_id: int) -> list[Case]:
    return list((await s.scalars(select(Case).where(Case.tg_id == tg_id).order_by(Case.id))).all())


async def get_case(s: AsyncSession, tg_id: int, case_id: int) -> Case | None:
    return await s.scalar(select(Case).where(Case.id == case_id, Case.tg_id == tg_id))


async def create_case(
    s: AsyncSession,
    tg_id: int,
    voiv: Voivodeship,
    purpose: Purpose,
    channel: Channel,
    filed: date,
    client_token: str,
) -> Case:
    existing = await s.scalar(select(Case).where(Case.client_token == client_token))
    if existing is not None:
        if existing.tg_id != tg_id:
            raise TokenConflict
        return existing
    if await count_cases(s, tg_id) >= MAX_CASES:
        raise TooManyCases
    case = Case(
        tg_id=tg_id, voivodeship=voiv, purpose=purpose, channel=channel, client_token=client_token
    )
    s.add(case)
    await s.flush()
    await set_milestone(s, case, Milestone.filed, filed)
    return case


async def delete_case(s: AsyncSession, case: Case, recompute: bool = True) -> None:
    """`recompute=False` leaves aggregates to the caller (the importer batches them)."""
    voiv, purpose, case_id = case.voivodeship, case.purpose, case.id
    # Pending upserts would recreate events for a case that no longer exists.
    await s.execute(delete(OutboxRow).where(OutboxRow.case_id == case_id, OutboxRow.op == "upsert"))
    # Queue a delete for every milestone, not only those with a recorded event: an insert
    # may be in flight. The worker resolves the event id when it processes the delete.
    milestones = {m.milestone for m in case.milestones}
    known = (
        await s.scalars(select(CalendarEvent.milestone).where(CalendarEvent.case_id == case_id))
    ).all()
    for m in sorted(milestones | set(known)):
        s.add(OutboxRow(op="delete", case_id=case_id, milestone=m))
    await s.delete(case)
    await s.flush()
    if recompute:
        await recompute_for(s, voiv, purpose)


# --- milestones ----------------------------------------------------------


async def _upsert_milestone(
    s: AsyncSession, case_id: int, milestone: str, d: date, confirmed_outlier: bool = False
) -> None:
    await s.execute(
        insert(MilestoneRow)
        .values(case_id=case_id, milestone=milestone, date=d, confirmed_outlier=confirmed_outlier)
        .on_conflict_do_update(
            index_elements=["case_id", "milestone"],
            set_={"date": d, "confirmed_outlier": confirmed_outlier},
        )
    )


async def _drop_milestone(s: AsyncSession, case: Case, milestone: str) -> None:
    """Remove the date and queue the removal of its calendar event."""
    await s.execute(
        delete(MilestoneRow).where(
            MilestoneRow.case_id == case.id, MilestoneRow.milestone == milestone
        )
    )
    await s.execute(
        delete(OutboxRow).where(
            OutboxRow.case_id == case.id,
            OutboxRow.milestone == milestone,
            OutboxRow.op == "upsert",
        )
    )
    s.add(OutboxRow(op="delete", case_id=case.id, milestone=milestone))


async def set_milestone(
    s: AsyncSession, case: Case, milestone: Milestone, d: date, confirmed_outlier: bool = False
) -> None:
    await _upsert_milestone(s, case.id, milestone, d, confirmed_outlier)
    await s.flush()
    await s.refresh(case, ["milestones"])
    await _enqueue_case_upserts(s, case)
    await recompute_for(s, case.voivodeship, case.purpose)


async def clear_milestone(s: AsyncSession, case: Case, milestone: Milestone) -> None:
    if milestone == Milestone.filed:
        raise ValueError("filed cannot be cleared")
    await _drop_milestone(s, case, milestone)
    await s.flush()
    await s.refresh(case, ["milestones"])
    await recompute_for(s, case.voivodeship, case.purpose)


# --- imported cases --------------------------------------------------------
# Owned by SYSTEM_TG_ID. These write dates and queue calendar changes like the functions
# above but leave aggregates to the caller, which recomputes each affected key once.


async def import_case(
    s: AsyncSession,
    client_token: str,
    voiv: Voivodeship,
    purpose: Purpose,
    channel: Channel,
    dates: dict[Milestone, date],
) -> Case:
    if Milestone.filed not in dates:
        raise ValueError("an imported case needs a filing date")
    case = Case(
        tg_id=SYSTEM_TG_ID,
        voivodeship=voiv,
        purpose=purpose,
        channel=channel,
        client_token=client_token,
    )
    s.add(case)
    await s.flush()
    await s.execute(
        insert(MilestoneRow).values(
            [{"case_id": case.id, "milestone": str(m), "date": d} for m, d in dates.items()]
        )
    )
    await s.flush()
    await s.refresh(case, ["milestones"])
    await _enqueue_case_upserts(s, case)
    return case


async def write_dates(s: AsyncSession, case: Case, dates: dict[Milestone, date]) -> bool:
    """Make the case's dates exactly `dates`; False when nothing changed."""
    if Milestone.filed not in dates:
        raise ValueError("an imported case needs a filing date")
    current = case.dates()
    if current == dates:
        return False
    for m in sorted(set(current) - set(dates)):
        await _drop_milestone(s, case, m)
    for m, d in dates.items():
        if current.get(m) != d:
            await _upsert_milestone(s, case.id, m, d)
    await s.flush()
    await s.refresh(case, ["milestones"])
    await _enqueue_case_upserts(s, case)
    return True


def calendar_payload(case: Case, milestone: str, d: date) -> dict:
    """One event per milestone; every event carries the case's full anonymous timeline."""
    dates = {Milestone(k): v for k, v in case.dates().items()}
    filed = dates[Milestone.filed]
    voiv = VOIV_LABELS[Voivodeship(case.voivodeship)]
    purpose = PURPOSE_LABELS[Purpose(case.purpose)]
    title = " · ".join([voiv, purpose, MILESTONE_LABELS[Milestone(milestone)]])
    lines = [f"{voiv} · {purpose}"]
    for m in Milestone:
        if m not in dates:
            continue
        line = f"{MILESTONE_LABELS[m]} — {dates[m]:%d.%m.%Y}"
        if m != Milestone.filed:
            line += f" (+{(dates[m] - filed).days} дн.)"
        lines.append(line)
    lines.append("")
    if IMPORT_SOURCE_LINE and getattr(case, "tg_id", None) == SYSTEM_TG_ID:
        lines.append(IMPORT_SOURCE_LINE)
    lines.append("Анонимные данные из @czekachiko_bot")
    return {"title": title, "date": d.isoformat(), "description": "\n".join(lines)}


async def _enqueue_case_upserts(s: AsyncSession, case: Case) -> None:
    # Every milestone description carries the filing month, so a change to any date
    # refreshes the whole case.
    await s.execute(delete(OutboxRow).where(OutboxRow.case_id == case.id, OutboxRow.op == "upsert"))
    for m in case.milestones:
        s.add(
            OutboxRow(
                op="upsert",
                case_id=case.id,
                milestone=m.milestone,
                payload=calendar_payload(case, m.milestone, m.date),
            )
        )
    await s.flush()


async def record_event_id(
    s: AsyncSession, case_id: int, milestone: str, event_id: str, scope: str = "all"
) -> None:
    await s.execute(
        insert(CalendarEvent)
        .values(case_id=case_id, milestone=milestone, scope=scope, event_id=event_id)
        .on_conflict_do_update(
            index_elements=["case_id", "milestone", "scope"], set_={"event_id": event_id}
        )
    )


async def calendar_links(s: AsyncSession) -> dict[str, str]:
    return {r.scope: r.calendar_id for r in (await s.scalars(select(CalendarRow))).all()}


async def set_calendar(s: AsyncSession, scope: str, calendar_id: str) -> None:
    await s.execute(
        insert(CalendarRow)
        .values(scope=scope, calendar_id=calendar_id)
        .on_conflict_do_update(index_elements=["scope"], set_={"calendar_id": calendar_id})
    )


# --- statistics ----------------------------------------------------------

PurposeSet = Purpose | str | Iterable[Purpose | str]

_INTERVALS_SQL = """
SELECT (b.date - a.date) AS days
FROM milestones a
JOIN milestones b ON b.case_id = a.case_id AND b.milestone = :to_m
JOIN cases c ON c.id = a.case_id
WHERE a.milestone = :from_m AND c.purpose = ANY(CAST(:purposes AS text[]))
  AND (CAST(:voiv AS text) IS NULL OR c.voivodeship = :voiv)
"""

# Every chain step (filing to each later milestone) in one round trip.
_CHAIN_SQL = """
SELECT b.milestone, (b.date - a.date) AS days
FROM milestones a
JOIN milestones b ON b.case_id = a.case_id AND b.milestone = ANY(CAST(:to_ms AS text[]))
JOIN cases c ON c.id = a.case_id
WHERE a.milestone = 'filed' AND c.purpose = ANY(CAST(:purposes AS text[]))
  AND (CAST(:voiv AS text) IS NULL OR c.voivodeship = :voiv)
"""


def _purpose_list(purpose: PurposeSet) -> list[str]:
    """One purpose (a str or Purpose) or several, as plain strings."""
    if isinstance(purpose, str):
        return [str(purpose)]
    return [str(p) for p in purpose]


async def interval_values(
    s: AsyncSession,
    scope: Literal["voiv", "national"],
    voiv: Voivodeship | str | None,
    purpose: PurposeSet,
    from_m: Milestone,
    to_m: Milestone,
) -> list[int]:
    """Day counts from `from_m` to `to_m` for one purpose or a set of them."""
    params = {
        "voiv": str(voiv) if scope == "voiv" else None,
        "purposes": _purpose_list(purpose),
        "from_m": str(from_m),
        "to_m": str(to_m),
    }
    return list((await s.execute(text(_INTERVALS_SQL), params)).scalars().all())


async def live_chain(
    s: AsyncSession, voiv: Voivodeship | str | None, purposes: PurposeSet
) -> dict[tuple[Milestone, Milestone], Aggregate | None]:
    """The chain computed from intervals: for purpose sets the aggregates table has no row for.

    `voiv=None` means all of Poland. One query whatever the number of purposes.
    """
    params = {
        "voiv": str(voiv) if voiv is not None else None,
        "purposes": _purpose_list(purposes),
        "to_ms": [str(b) for _, b in CHAIN],
    }
    values: dict[str, list[int]] = {}
    for milestone, days in (await s.execute(text(_CHAIN_SQL), params)).all():
        values.setdefault(milestone, []).append(days)
    return {(a, b): aggregate(values.get(str(b), [])) for a, b in CHAIN}


async def get_aggregate(
    s: AsyncSession,
    voiv: Voivodeship | str | None,
    purpose: Purpose | str,
    from_m: Milestone,
    to_m: Milestone,
) -> Aggregate | None:
    voiv_cond = (
        AggregateRow.voivodeship.is_(None)
        if voiv is None
        else AggregateRow.voivodeship == str(voiv)
    )
    row = await s.scalar(
        select(AggregateRow).where(
            voiv_cond,
            AggregateRow.purpose == str(purpose),
            AggregateRow.from_m == str(from_m),
            AggregateRow.to_m == str(to_m),
        )
    )
    if row is None:
        return None
    mean = row.mean if row.mean is not None else row.median
    return Aggregate(row.n, row.p10, row.median, row.p90, row.min, row.max, mean)


async def _recompute_key(s: AsyncSession, voiv: str | None, purpose: str, a: str, b: str) -> None:
    scope = "national" if voiv is None else "voiv"
    agg = aggregate(await interval_values(s, scope, voiv, purpose, a, b))
    if agg is None:
        voiv_cond = (
            AggregateRow.voivodeship.is_(None) if voiv is None else AggregateRow.voivodeship == voiv
        )
        await s.execute(
            delete(AggregateRow).where(
                voiv_cond,
                AggregateRow.purpose == purpose,
                AggregateRow.from_m == a,
                AggregateRow.to_m == b,
            )
        )
        return
    values = {
        "n": agg.n,
        "p10": agg.p10,
        "median": agg.median,
        "p90": agg.p90,
        "min": agg.min,
        "max": agg.max,
        "mean": agg.mean,
    }
    await s.execute(
        insert(AggregateRow)
        .values(voivodeship=voiv, purpose=purpose, from_m=a, to_m=b, **values)
        .on_conflict_do_update(
            index_elements=["voivodeship", "purpose", "from_m", "to_m"],
            set_={**values, "updated_at": func.now()},
        )
    )


async def recompute_for(s: AsyncSession, voiv: str, purpose: str) -> None:
    """Recompute every interval pair for one voivodeship + purpose and its national key.

    Writers of the same purpose share the national key, so they are serialized with a
    transaction-scoped advisory lock; the next writer then reads the committed data.
    """
    await recompute_many(s, [(voiv, purpose)])


async def recompute_many(s: AsyncSession, keys) -> None:
    """recompute_for over several (voivodeship, purpose) keys, each national key once.

    Locks are taken in purpose order, so two batch writers cannot deadlock each other.
    """
    keys = sorted({(str(v), str(p)) for v, p in keys})
    purposes = sorted({p for _, p in keys})
    for p in purposes:
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"agg:{p}"})
    for v, p in keys:
        for a, b in INTERVAL_PAIRS:
            await _recompute_key(s, v, p, str(a), str(b))
    for p in purposes:
        for a, b in INTERVAL_PAIRS:
            await _recompute_key(s, None, p, str(a), str(b))
    await s.flush()


async def chain_aggregates(
    s: AsyncSession, voiv: Voivodeship | str | None, purpose: Purpose | str
) -> dict[tuple[Milestone, Milestone], Aggregate | None]:
    """One purpose from the aggregates table; `voiv=None` reads the national rows."""
    return {(a, b): await get_aggregate(s, voiv, purpose, a, b) for a, b in CHAIN}


async def chain_keys(s: AsyncSession) -> set[tuple[str, str]]:
    """(voivodeship, purpose) pairs with at least one chain aggregate.

    The same test as `any(chain_aggregates(...).values())`: the chain is every interval
    from filing, and those are exactly the aggregate rows with from_m = 'filed'.
    """
    rows = await s.execute(
        select(AggregateRow.voivodeship, AggregateRow.purpose)
        .where(AggregateRow.voivodeship.is_not(None), AggregateRow.from_m == str(Milestone.filed))
        .distinct()
    )
    return {(v, p) for v, p in rows.all()}


async def recompute_all(s: AsyncSession) -> None:
    await s.execute(delete(AggregateRow))
    combos = (await s.execute(select(Case.voivodeship, Case.purpose).distinct())).all()
    for voiv, purpose in combos:
        await recompute_for(s, voiv, purpose)


async def recent_events(
    s: AsyncSession,
    voiv: Voivodeship | str | None,
    purpose: PurposeSet,
    milestone: Milestone,
    since: date,
) -> list[tuple[date, date]]:
    """(milestone date, filing date) since `since`; `voiv=None` means all of Poland."""
    sql = text(
        """
        SELECT m.date, f.date FROM milestones m
        JOIN milestones f ON f.case_id = m.case_id AND f.milestone = 'filed'
        JOIN cases c ON c.id = m.case_id
        WHERE m.milestone = :m AND m.date >= :since
          AND (CAST(:voiv AS text) IS NULL OR c.voivodeship = :voiv)
          AND c.purpose = ANY(CAST(:purposes AS text[]))
        ORDER BY m.date
        """
    )
    params = {
        "m": str(milestone),
        "since": since,
        "voiv": str(voiv) if voiv is not None else None,
        "purposes": _purpose_list(purpose),
    }
    rows = await s.execute(sql, params)
    return [(a, b) for a, b in rows.all()]


async def case_counts(s: AsyncSession, users_only: bool = False) -> list[tuple[str, int]]:
    """Cases per voivodeship, most first; `users_only` leaves imported cases out."""
    query = select(Case.voivodeship, func.count())
    if users_only:
        query = query.where(Case.tg_id != SYSTEM_TG_ID)
    rows = await s.execute(query.group_by(Case.voivodeship).order_by(func.count().desc()))
    return [(v, n) for v, n in rows.all()]


async def admin_counts(s: AsyncSession) -> list[tuple[str, int]]:
    """People's own cases per voivodeship; imported ones are counted apart."""
    return await case_counts(s, users_only=True)


async def count_imported(s: AsyncSession) -> int:
    return await s.scalar(select(func.count()).select_from(Case).where(Case.tg_id == SYSTEM_TG_ID))


async def admin_recent(s: AsyncSession, limit: int = 10) -> list[Case]:
    query = select(Case).where(Case.tg_id != SYSTEM_TG_ID).order_by(Case.id.desc()).limit(limit)
    return list((await s.scalars(query)).all())


# --- feedback --------------------------------------------------------------


async def add_feedback(s: AsyncSession, tg_id: int, direction: str, text_: str) -> Feedback:
    await ensure_user(s, tg_id)
    row = Feedback(tg_id=tg_id, direction=direction, text=text_[:1000])
    s.add(row)
    await s.flush()
    return row


async def count_feedback_since(s: AsyncSession, tg_id: int, since) -> int:
    """Counts from the content-free log, so deleting data never resets the limit."""
    return await s.scalar(
        select(func.count())
        .select_from(FeedbackRate)
        .where(FeedbackRate.tg_id == tg_id, FeedbackRate.created_at >= since)
    )


async def log_feedback_send(s: AsyncSession, tg_id: int) -> None:
    s.add(FeedbackRate(tg_id=tg_id))
    # Keep the log small: older entries no longer affect any limit.
    await s.execute(
        delete(FeedbackRate).where(FeedbackRate.created_at < func.now() - text("interval '1 day'"))
    )
    await s.flush()


async def feedback_by_admin_msg(s: AsyncSession, admin_msg_id: int) -> Feedback | None:
    return await s.scalar(
        select(Feedback).where(Feedback.admin_msg_id == admin_msg_id, Feedback.direction == "in")
    )


# --- documents -------------------------------------------------------------
# The owner's checklist. Every function takes a case the caller loaded with get_case, so a
# document is only reachable through its owner. Nothing here touches aggregates or the
# calendar outbox.


class TooManyDocs(Exception):
    pass


async def list_docs(s: AsyncSession, case: Case) -> list[CaseDocument]:
    query = (
        select(CaseDocument)
        .where(CaseDocument.case_id == case.id)
        .order_by(CaseDocument.id)
        .execution_options(populate_existing=True)  # upserts bypass the identity map
    )
    return list((await s.scalars(query)).all())


async def set_standard_doc(s: AsyncSession, case: Case, code: str, d: date | None) -> None:
    """Tick (or re-date) a standard item; None un-ticks it."""
    if code not in documents.checklist(case.purpose):
        raise ValueError(f"{code!r} is not on the {case.purpose} checklist")
    if d is None:
        await s.execute(
            delete(CaseDocument).where(CaseDocument.case_id == case.id, CaseDocument.code == code)
        )
    else:
        await s.execute(
            insert(CaseDocument)
            .values(case_id=case.id, code=code, submitted_on=d)
            .on_conflict_do_update(index_elements=["case_id", "code"], set_={"submitted_on": d})
        )
    await s.flush()


async def count_custom_docs(s: AsyncSession, case: Case) -> int:
    return await s.scalar(
        select(func.count())
        .select_from(CaseDocument)
        .where(CaseDocument.case_id == case.id, CaseDocument.name.is_not(None))
    )


async def get_custom_doc(s: AsyncSession, case: Case, doc_id: int) -> CaseDocument | None:
    return await s.scalar(
        select(CaseDocument).where(
            CaseDocument.id == doc_id,
            CaseDocument.case_id == case.id,
            CaseDocument.name.is_not(None),
        )
    )


def _valid_name(name: str) -> str:
    cleaned, error = documents.clean_name(name)
    if error:
        raise ValueError(error)
    return cleaned


async def add_custom_doc(s: AsyncSession, case: Case, name: str, d: date | None) -> CaseDocument:
    name = _valid_name(name)
    if await count_custom_docs(s, case) >= documents.MAX_CUSTOM:
        raise TooManyDocs
    doc = CaseDocument(case_id=case.id, name=name, submitted_on=d)
    s.add(doc)
    await s.flush()
    return doc


async def rename_custom_doc(s: AsyncSession, doc: CaseDocument, name: str) -> None:
    doc.name = _valid_name(name)
    await s.flush()


async def set_doc_date(s: AsyncSession, doc: CaseDocument, d: date | None) -> None:
    doc.submitted_on = d
    await s.flush()


async def delete_custom_doc(s: AsyncSession, doc: CaseDocument) -> None:
    await s.delete(doc)
    await s.flush()
