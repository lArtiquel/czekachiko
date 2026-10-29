"""Data access. Functions flush but never commit: the caller owns the transaction."""

from datetime import date
from typing import Literal

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db.models import (
    AggregateRow,
    CalendarEvent,
    Case,
    Feedback,
    MilestoneRow,
    OutboxRow,
    User,
)
from czekachiko.domain import CHAIN, INTERVAL_PAIRS, Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales.ru import MILESTONE_LABELS, PURPOSE_LABELS, VOIV_LABELS
from czekachiko.stats import Aggregate, aggregate

MAX_CASES = 5


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


async def set_reminders(s: AsyncSession, tg_id: int, on: bool) -> None:
    (await ensure_user(s, tg_id)).reminders = on
    await s.flush()


async def delete_user(s: AsyncSession, tg_id: int) -> None:
    for case in await list_cases(s, tg_id):
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


async def delete_case(s: AsyncSession, case: Case) -> None:
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
    await recompute_for(s, voiv, purpose)


# --- milestones ----------------------------------------------------------


async def set_milestone(
    s: AsyncSession, case: Case, milestone: Milestone, d: date, confirmed_outlier: bool = False
) -> None:
    await s.execute(
        insert(MilestoneRow)
        .values(case_id=case.id, milestone=milestone, date=d, confirmed_outlier=confirmed_outlier)
        .on_conflict_do_update(
            index_elements=["case_id", "milestone"],
            set_={"date": d, "confirmed_outlier": confirmed_outlier},
        )
    )
    await s.flush()
    await s.refresh(case, ["milestones"])
    await _enqueue_case_upserts(s, case)
    await recompute_for(s, case.voivodeship, case.purpose)


async def clear_milestone(s: AsyncSession, case: Case, milestone: Milestone) -> None:
    if milestone == Milestone.filed:
        raise ValueError("filed cannot be cleared")
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
    await s.flush()
    await s.refresh(case, ["milestones"])
    await recompute_for(s, case.voivodeship, case.purpose)


def calendar_payload(case: Case, milestone: str, d: date) -> dict:
    filed = case.dates()[Milestone.filed]
    title = " · ".join(
        [
            VOIV_LABELS[Voivodeship(case.voivodeship)],
            PURPOSE_LABELS[Purpose(case.purpose)],
            MILESTONE_LABELS[Milestone(milestone)],
        ]
    )
    return {"title": title, "date": d.isoformat(), "description": f"подано {filed:%m.%Y}"}


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


async def record_event_id(s: AsyncSession, case_id: int, milestone: str, event_id: str) -> None:
    await s.execute(
        insert(CalendarEvent)
        .values(case_id=case_id, milestone=milestone, event_id=event_id)
        .on_conflict_do_update(index_elements=["case_id", "milestone"], set_={"event_id": event_id})
    )


# --- statistics ----------------------------------------------------------

_INTERVALS_SQL = """
SELECT (b.date - a.date) AS days
FROM milestones a
JOIN milestones b ON b.case_id = a.case_id AND b.milestone = :to_m
JOIN cases c ON c.id = a.case_id
WHERE a.milestone = :from_m AND c.purpose = :purpose
  AND (CAST(:voiv AS text) IS NULL OR c.voivodeship = :voiv)
"""


async def interval_values(
    s: AsyncSession,
    scope: Literal["voiv", "national"],
    voiv: Voivodeship | str | None,
    purpose: Purpose | str,
    from_m: Milestone,
    to_m: Milestone,
) -> list[int]:
    params = {
        "voiv": str(voiv) if scope == "voiv" else None,
        "purpose": str(purpose),
        "from_m": str(from_m),
        "to_m": str(to_m),
    }
    return list((await s.execute(text(_INTERVALS_SQL), params)).scalars().all())


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
    await s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"agg:{purpose}"})
    for a, b in INTERVAL_PAIRS:
        await _recompute_key(s, str(voiv), str(purpose), str(a), str(b))
        await _recompute_key(s, None, str(purpose), str(a), str(b))
    await s.flush()


async def chain_aggregates(
    s: AsyncSession, voiv: Voivodeship | str, purpose: Purpose | str
) -> dict[tuple[Milestone, Milestone], Aggregate | None]:
    return {(a, b): await get_aggregate(s, voiv, purpose, a, b) for a, b in CHAIN}


async def recompute_all(s: AsyncSession) -> None:
    await s.execute(delete(AggregateRow))
    combos = (await s.execute(select(Case.voivodeship, Case.purpose).distinct())).all()
    for voiv, purpose in combos:
        await recompute_for(s, voiv, purpose)


async def recent_events(
    s: AsyncSession,
    voiv: Voivodeship | str,
    purpose: Purpose | str,
    milestone: Milestone,
    since: date,
) -> list[tuple[date, date]]:
    sql = text(
        """
        SELECT m.date, f.date FROM milestones m
        JOIN milestones f ON f.case_id = m.case_id AND f.milestone = 'filed'
        JOIN cases c ON c.id = m.case_id
        WHERE m.milestone = :m AND m.date >= :since AND c.voivodeship = :voiv
          AND c.purpose = :purpose
        ORDER BY m.date
        """
    )
    rows = await s.execute(
        sql, {"m": str(milestone), "since": since, "voiv": str(voiv), "purpose": str(purpose)}
    )
    return [(a, b) for a, b in rows.all()]


async def admin_counts(s: AsyncSession) -> list[tuple[str, int]]:
    rows = await s.execute(
        select(Case.voivodeship, func.count())
        .group_by(Case.voivodeship)
        .order_by(func.count().desc())
    )
    return [(v, n) for v, n in rows.all()]


async def admin_recent(s: AsyncSession, limit: int = 10) -> list[Case]:
    return list((await s.scalars(select(Case).order_by(Case.id.desc()).limit(limit))).all())


# --- feedback --------------------------------------------------------------


async def add_feedback(s: AsyncSession, tg_id: int, direction: str, text_: str) -> Feedback:
    await ensure_user(s, tg_id)
    row = Feedback(tg_id=tg_id, direction=direction, text=text_[:1000])
    s.add(row)
    await s.flush()
    return row


async def count_feedback_since(s: AsyncSession, tg_id: int, since) -> int:
    return await s.scalar(
        select(func.count())
        .select_from(Feedback)
        .where(Feedback.tg_id == tg_id, Feedback.direction == "in", Feedback.created_at >= since)
    )


async def feedback_by_admin_msg(s: AsyncSession, admin_msg_id: int) -> Feedback | None:
    return await s.scalar(
        select(Feedback).where(Feedback.admin_msg_id == admin_msg_id, Feedback.direction == "in")
    )
