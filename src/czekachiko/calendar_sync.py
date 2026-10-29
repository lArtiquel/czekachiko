"""Mirror milestones into the public Google Calendar via the DB outbox."""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from czekachiko.db import repo
from czekachiko.db.models import CalendarEvent, Case, MilestoneRow, OutboxRow

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

    async def delete(self, calendar_id, event_id) -> None:
        r = await self.http.delete(
            f"{API}/{calendar_id}/events/{event_id}", headers=await self._headers()
        )
        if r.status_code not in (404, 410):
            r.raise_for_status()


async def _milestone_exists(s, case_id: int, milestone: str) -> bool:
    return await s.get(MilestoneRow, (case_id, milestone)) is not None


async def _process(s, row: OutboxRow, client: CalendarClient, calendar_id: str) -> None:
    mapping = await s.get(CalendarEvent, (row.case_id, row.milestone))
    if row.op == "delete":
        if mapping is not None:
            await client.delete(calendar_id, mapping.event_id)
            await s.delete(mapping)
        return
    if await s.get(Case, row.case_id) is None or not await _milestone_exists(
        s, row.case_id, row.milestone
    ):
        return  # case or milestone gone; a delete row handles any existing event
    p = row.payload
    day = date.fromisoformat(p["date"])
    if mapping is not None:
        await client.update(calendar_id, mapping.event_id, p["title"], day, p["description"])
        return
    event_id = await client.insert(calendar_id, p["title"], day, p["description"])
    await repo.record_event_id(s, row.case_id, row.milestone, event_id)
    await s.flush()
    # The case may have been deleted while the insert was in flight.
    await s.refresh(row)
    if await s.get(Case, row.case_id, populate_existing=True) is None:
        await client.delete(calendar_id, event_id)
        await s.execute(
            delete(CalendarEvent).where(
                CalendarEvent.case_id == row.case_id, CalendarEvent.milestone == row.milestone
            )
        )


async def drain_outbox(
    factory: async_sessionmaker,
    client: CalendarClient,
    calendar_id: str,
    now: datetime,
    batch: int = 50,
) -> int:
    async with factory() as s:
        ids = (
            await s.scalars(
                select(OutboxRow.id)
                .where(OutboxRow.next_try_at <= now)
                .order_by(OutboxRow.id)
                .limit(batch)
            )
        ).all()
    done = 0
    for row_id in ids:
        async with factory() as s:
            row = await s.get(OutboxRow, row_id)
            if row is None:
                continue
            try:
                await _process(s, row, client, calendar_id)
                await s.delete(row)
                await s.commit()
                done += 1
            except Exception as e:  # noqa: BLE001 — one bad row must not stop the queue
                await s.rollback()
                row = await s.get(OutboxRow, row_id)
                if row is not None:
                    row.attempts += 1
                    row.next_try_at = now + timedelta(minutes=min(2**row.attempts, 360))
                    await s.commit()
                log.warning(
                    "calendar sync failed (row %s, attempt %s): %s",
                    row_id,
                    row.attempts if row else "?",
                    type(e).__name__,
                )
    return done


async def run_calendar_worker(
    factory: async_sessionmaker, client: CalendarClient, calendar_id: str, interval: float = 30
) -> None:
    while True:
        try:
            await drain_outbox(factory, client, calendar_id, datetime.now(UTC))
        except Exception:  # noqa: BLE001
            log.exception("calendar worker iteration failed")
        await asyncio.sleep(interval)


def start_worker(settings, factory: async_sessionmaker) -> asyncio.Task:
    client = GoogleCalendarClient(settings.google_service_account_json)
    return asyncio.create_task(run_calendar_worker(factory, client, settings.calendar_id))
