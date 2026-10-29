from datetime import date

from czekachiko.app import build_dispatcher
from czekachiko.db import repo
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


async def test_admin_recompute(session_factory):
    dp, bot, tg = await setup(session_factory)
    await dp.feed_update(bot, text_update(ADMIN, "/admin recompute"))
    assert "Пересчитано" in tg.last().text
