from datetime import date

from sqlalchemy import delete, select

from czekachiko.app import build_dispatcher
from czekachiko.db import repo
from czekachiko.db.models import OutboxRow
from czekachiko.domain import Channel, Purpose, Voivodeship
from czekachiko.locales import ru
from tests.fakes import make_bot, text_update

ADMIN = 777


async def setup(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory,
        clock=lambda: date(2026, 10, 29),
        admin_tg_id=ADMIN,
        throttle=False,
    )
    return dp, bot, tg


async def test_admin_hidden_for_others(session_factory):
    dp, bot, tg = await setup(session_factory)
    for command in ("/admin", "/admin recompute"):
        await dp.feed_update(bot, text_update(1, command))
        assert tg.last().text == ru.MESSAGES["unknown_message"]


async def test_admin_shows_counts(session_factory):
    async with session_factory() as s:
        await repo.ensure_user(s, 5)
        await repo.create_case(
            s, 5, Voivodeship.mazowieckie, Purpose.jdg, Channel.mos, date(2026, 3, 6), "a"
        )
        await s.commit()
    dp, bot, tg = await setup(session_factory)
    await dp.feed_update(bot, text_update(ADMIN, "/admin"))
    assert "Admin" in tg.last().text and "Mazowieckie: 1" in tg.last().text
    assert "\nuser: 1\n" in tg.last().text  # cases by source


async def test_admin_calendar_queues_every_event(session_factory):
    async with session_factory() as s:
        await repo.ensure_user(s, 5)
        await repo.create_case(
            s, 5, Voivodeship.mazowieckie, Purpose.jdg, Channel.mos, date(2026, 3, 6), "a"
        )
        await s.execute(delete(OutboxRow))
        await s.commit()
    dp, bot, tg = await setup(session_factory)
    await dp.feed_update(bot, text_update(ADMIN, "/admin calendar"))
    async with session_factory() as s:
        queued = (await s.scalars(select(OutboxRow))).all()
    assert [(r.op, r.milestone) for r in queued] == [("upsert", "filed")]
    assert "1" in tg.last().text
    await dp.feed_update(bot, text_update(1, "/admin calendar"))
    assert tg.last().text == ru.MESSAGES["unknown_message"]


async def test_admin_recompute(session_factory):
    dp, bot, tg = await setup(session_factory)
    await dp.feed_update(bot, text_update(ADMIN, "/admin recompute"))
    assert "Пересчитано" in tg.last().text
