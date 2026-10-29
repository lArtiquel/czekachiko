from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from czekachiko.calendar_sync import drain_outbox
from czekachiko.db import repo
from czekachiko.db.models import CalendarEvent, OutboxRow
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship

NOW = datetime.now(UTC) + timedelta(hours=1)  # rows default next_try_at=now()
CAL = "cal@group.calendar.google.com"


class FakeCalendar:
    def __init__(self, fail=False):
        self.fail = fail
        self.events: dict[str, dict] = {}
        self.log: list[tuple] = []
        self._n = 0

    async def insert(self, calendar_id, title, day, description):
        if self.fail:
            raise RuntimeError("boom")
        self._n += 1
        eid = f"e{self._n}"
        self.events[eid] = {"title": title, "day": day}
        self.log.append(("insert", eid))
        return eid

    async def update(self, calendar_id, event_id, title, day, description):
        self.events[event_id] = {"title": title, "day": day}
        self.log.append(("update", event_id))

    async def delete(self, calendar_id, event_id):
        self.events.pop(event_id, None)
        self.log.append(("delete", event_id))


async def new_case(s, uid=1, token="t"):
    await repo.ensure_user(s, uid)
    c = await repo.create_case(
        s, uid, Voivodeship.mazowieckie, Purpose.jdg, Channel.paper, date(2026, 3, 6), token
    )
    await s.commit()
    return c


async def test_drain_inserts_and_records_event_id(session_factory):
    async with session_factory() as s:
        c = await new_case(s)
    cal = FakeCalendar()
    assert await drain_outbox(session_factory, cal, CAL, NOW) == 1
    async with session_factory() as s:
        ev = await s.get(CalendarEvent, (c.id, "filed"))
        assert ev.event_id == "e1"
        assert (await s.scalars(select(OutboxRow))).all() == []
    assert cal.events["e1"]["title"] == "Mazowieckie · art. 142 · подача"


async def test_drain_update_uses_existing_event_id(session_factory):
    async with session_factory() as s:
        c = await new_case(s)
    cal = FakeCalendar()
    await drain_outbox(session_factory, cal, CAL, NOW)
    async with session_factory() as s:
        c = await repo.get_case(s, 1, c.id)
        await repo.set_milestone(s, c, Milestone.filed, date(2026, 3, 7))
        await s.commit()
    await drain_outbox(session_factory, cal, CAL, NOW)
    assert cal.log == [("insert", "e1"), ("update", "e1")]


async def test_drain_failure_backs_off(session_factory):
    async with session_factory() as s:
        await new_case(s)
    await drain_outbox(session_factory, FakeCalendar(fail=True), CAL, NOW)
    async with session_factory() as s:
        row = (await s.scalars(select(OutboxRow))).one()
    assert row.attempts == 1 and row.next_try_at > NOW


async def test_delete_after_insert_removes_event(session_factory):
    async with session_factory() as s:
        c = await new_case(s)
    cal = FakeCalendar()
    await drain_outbox(session_factory, cal, CAL, NOW)
    async with session_factory() as s:
        await repo.delete_case(s, await repo.get_case(s, 1, c.id))
        await s.commit()
    await drain_outbox(session_factory, cal, CAL, NOW)
    assert cal.events == {}
    async with session_factory() as s:
        assert await s.get(CalendarEvent, (c.id, "filed")) is None


async def test_upsert_for_deleted_case_is_dropped(session_factory):
    async with session_factory() as s:
        c = await new_case(s)
        s.add(
            OutboxRow(
                op="upsert",
                case_id=999,
                milestone="filed",
                payload={"title": "x", "date": "2026-03-06", "description": "y"},
            )
        )
        await s.commit()
    cal = FakeCalendar()
    await drain_outbox(session_factory, cal, CAL, NOW)
    assert list(cal.events) == ["e1"]  # only the real case's event
    assert c.id != 999
