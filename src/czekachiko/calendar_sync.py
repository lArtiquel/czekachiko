"""Mirror milestones into the public Google Calendar via the DB outbox."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from urllib.parse import quote

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from czekachiko.db import repo
from czekachiko.db.models import CalendarEvent, CalendarRow, Case, MilestoneRow, OutboxRow

log = logging.getLogger(__name__)
API = "https://www.googleapis.com/calendar/v3/calendars"
SCOPE = "https://www.googleapis.com/auth/calendar"


class CalendarClient(Protocol):
    async def insert(self, calendar_id: str, title: str, day: date, description: str) -> str: ...
    async def update(
        self, calendar_id: str, event_id: str, title: str, day: date, description: str
    ) -> None: ...
    async def delete(self, calendar_id: str, event_id: str) -> None: ...


class GoogleCalendarClient:
    def __init__(self, service_account_json_path: str):
        from google.oauth2 import service_account

        self.creds = service_account.Credentials.from_service_account_file(
            service_account_json_path, scopes=[SCOPE]
        )
        self.http = httpx.AsyncClient(timeout=20)

    async def _headers(self) -> dict[str, str]:
        if not self.creds.valid:
            from google.auth.transport.requests import Request

            await asyncio.to_thread(self.creds.refresh, Request())
        return {"Authorization": f"Bearer {self.creds.token}"}

    @staticmethod
    def _body(title: str, day: date, description: str) -> dict:
        return {
            "summary": title,
            "description": description,
            "start": {"date": day.isoformat()},
            "end": {"date": (day + timedelta(days=1)).isoformat()},
            "transparency": "transparent",
        }

    async def insert(self, calendar_id, title, day, description) -> str:
        r = await self.http.post(
            f"{API}/{calendar_id}/events",
            headers=await self._headers(),
            json=self._body(title, day, description),
        )
        r.raise_for_status()
        return r.json()["id"]

    async def update(self, calendar_id, event_id, title, day, description) -> None:
        r = await self.http.put(
            f"{API}/{calendar_id}/events/{event_id}",
            headers=await self._headers(),
            json=self._body(title, day, description),
        )
        r.raise_for_status()

    async def create_calendar(self, summary: str) -> str:
        """A new calendar owned by the service account, readable by everyone."""
        headers = await self._headers()
        r = await self.http.post(
            API,
            headers=headers,
            json={
                "summary": summary,
                "description": "Anonymous residence-permit milestones · t.me/czekachiko_bot",
                "timeZone": "Europe/Warsaw",
            },
        )
        r.raise_for_status()
        cid = r.json()["id"]
        r = await self.http.post(
            f"{API}/{quote(cid)}/acl",
            headers=headers,
            json={"role": "reader", "scope": {"type": "default"}},
        )
        r.raise_for_status()
        return cid

    async def delete(self, calendar_id, event_id) -> None:
        r = await self.http.delete(
            f"{API}/{calendar_id}/events/{event_id}", headers=await self._headers()
        )
        if r.status_code not in (404, 410):
            r.raise_for_status()


async def _milestone_exists(s, case_id: int, milestone: str) -> bool:
    return await s.get(MilestoneRow, (case_id, milestone)) is not None


async def _case_alive(factory: async_sessionmaker, case_id: int, milestone: str) -> bool:
    async with factory() as s:
        return await s.get(MilestoneRow, (case_id, milestone)) is not None


async def _calendar_for(factory: async_sessionmaker, scope: str, default_all: str) -> str | None:
    if scope == "all":
        return default_all
    async with factory() as s:
        row = await s.get(CalendarRow, scope)
        return row.calendar_id if row else None


async def _forget(factory: async_sessionmaker, case_id: int, milestone: str, scope: str) -> None:
    async with factory() as s:
        await s.execute(
            delete(CalendarEvent).where(
                CalendarEvent.case_id == case_id,
                CalendarEvent.milestone == milestone,
                CalendarEvent.scope == scope,
            )
        )
        await s.commit()


async def _process(
    factory: async_sessionmaker, row: OutboxRow, client: CalendarClient, calendar_id: str
) -> None:
    if row.op == "delete":
        async with factory() as s:
            mappings = (
                await s.scalars(
                    select(CalendarEvent).where(
                        CalendarEvent.case_id == row.case_id,
                        CalendarEvent.milestone == row.milestone,
                    )
                )
            ).all()
        for m in mappings:
            target = await _calendar_for(factory, m.scope, calendar_id)
            if target is not None:
                await client.delete(target, m.event_id)
            await _forget(factory, row.case_id, row.milestone, m.scope)
        return

    async with factory() as s:
        case = await s.get(Case, row.case_id)
        voiv = case.voivodeship if case else None
    if voiv is None or not await _case_alive(factory, row.case_id, row.milestone):
        return  # case or milestone gone; a delete row handles any existing event
    p = row.payload
    day = date.fromisoformat(p["date"])
    for scope in ("all", voiv):  # whole Poland + the case's voivodeship
        target = await _calendar_for(factory, scope, calendar_id)
        if target is None:
            continue
        async with factory() as s:
            mapping = await s.get(CalendarEvent, (row.case_id, row.milestone, scope))
            event_id = mapping.event_id if mapping else None
        if event_id is not None:
            await client.update(target, event_id, p["title"], day, p["description"])
            continue
        event_id = await client.insert(target, p["title"], day, p["description"])
        # Commit the mapping at once, so a delete or edit queued meanwhile can find the event.
        async with factory() as s:
            await repo.record_event_id(s, row.case_id, row.milestone, event_id, scope)
            await s.commit()
        if not await _case_alive(factory, row.case_id, row.milestone):
            # Deleted while the insert was in flight: remove the event now.
            await client.delete(target, event_id)
            await _forget(factory, row.case_id, row.milestone, scope)


async def ensure_calendars(factory: async_sessionmaker, client, all_calendar_id: str) -> None:
    """Record the whole-Poland calendar and create any missing per-voivodeship calendar."""
    from czekachiko.domain import Voivodeship
    from czekachiko.locales.ru import VOIV_LABELS

    async with factory() as s:
        await repo.set_calendar(s, "all", all_calendar_id)
        await s.commit()
        existing = await repo.calendar_links(s)
    for v in Voivodeship:
        if v.value in existing:
            continue
        cid = await client.create_calendar(f"Czekachiko · {VOIV_LABELS[v]}")
        async with factory() as s:
            await repo.set_calendar(s, v.value, cid)
            await s.commit()


async def drain_outbox(
    factory: async_sessionmaker,
    client: CalendarClient,
    calendar_id: str,
    now: datetime,
    batch: int = 50,
) -> int:
    async with factory() as s:
        rows = (
            await s.scalars(
                select(OutboxRow)
                .where(OutboxRow.next_try_at <= now)
                .order_by(OutboxRow.id)
                .limit(batch)
            )
        ).all()
    done = 0
    for row in rows:
        try:
            await _process(factory, row, client, calendar_id)
        except Exception as e:  # noqa: BLE001 — one bad row must not stop the queue
            async with factory() as s:
                attempts = row.attempts + 1
                await s.execute(
                    update(OutboxRow)
                    .where(OutboxRow.id == row.id)
                    .values(
                        attempts=attempts,
                        next_try_at=now + timedelta(minutes=min(2**attempts, 360)),
                    )
                )
                await s.commit()
            log.warning(
                "calendar sync failed (row %s, attempt %s): %s", row.id, attempts, type(e).__name__
            )
            continue
        async with factory() as s:
            # The row may already be gone (superseded by an edit or deletion): fine.
            await s.execute(delete(OutboxRow).where(OutboxRow.id == row.id))
            await s.commit()
        done += 1
    return done


async def run_calendar_worker(
    factory: async_sessionmaker, client: CalendarClient, calendar_id: str, interval: float = 30
) -> None:
    try:
        await ensure_calendars(factory, client, calendar_id)
    except Exception:  # noqa: BLE001 — voivodeship calendars are retried on next start
        log.exception("could not create voivodeship calendars")
    while True:
        try:
            await drain_outbox(factory, client, calendar_id, datetime.now(UTC))
        except Exception:  # noqa: BLE001
            log.exception("calendar worker iteration failed")
        await asyncio.sleep(interval)


def start_worker(settings, factory: async_sessionmaker) -> asyncio.Task | None:
    """Start the sync loop; a broken key disables the calendar but never the bot."""
    try:
        client = GoogleCalendarClient(settings.google_service_account_json)
    except Exception:  # noqa: BLE001
        log.exception("calendar disabled: cannot load service account key")
        return None
    return asyncio.create_task(run_calendar_worker(factory, client, settings.calendar_id))
