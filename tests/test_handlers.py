from datetime import date

import pytest

from czekachiko.app import build_dispatcher
from czekachiko.db import repo
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales import ru
from czekachiko.middlewares import ThrottleMiddleware
from czekachiko.ui.keyboards import Act, Day, Nav, Pick
from tests.fakes import callback_update, make_bot, text_update

UID = 548
TODAY = date(2026, 10, 29)


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory, clock=lambda: TODAY, admin_tg_id=None, calendar_url=None, throttle=False
    )
    yield dp, bot, tg, session_factory


async def feed(env, update):
    dp, bot, tg, _ = env
    await dp.feed_update(bot, update)


async def test_start_shows_menu_and_privacy(env):
    await feed(env, text_update(UID, "/start"))
    texts = env[2].texts()
    assert any("Czekachiko" in t for t in texts)
    assert any(ru.MESSAGES["privacy"][:20] in t for t in texts)


FILED = Day(y=2026, m=3, d=6)


async def drive_wizard(env, uid=UID, day=FILED):
    for data in [
        Nav(to="add"),
        Pick(field="voiv", value="mazowieckie"),
        Pick(field="purpose", value="jdg"),
        Pick(field="channel", value="paper"),
        day,
    ]:
        await feed(env, callback_update(uid, data.pack()))


async def test_add_wizard_creates_case(env):
    await drive_wizard(env)
    async with env[3]() as s:
        cases = await repo.list_cases(s, UID)
    assert len(cases) == 1
    assert cases[0].dates()[Milestone.filed] == date(2026, 3, 6)
    assert ru.MESSAGES["ask_more"][:10] in env[2].last().text


async def test_text_on_button_step_is_rejected(env):
    await feed(env, callback_update(UID, Nav(to="add").pack()))
    await feed(env, text_update(UID, "Mazowieckie"))
    assert ru.MESSAGES["err_use_buttons"] in env[2].texts()[-2]
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 0


async def test_typed_date_accepted(env):
    for data in [
        Nav(to="add"),
        Pick(field="voiv", value="mazowieckie"),
        Pick(field="purpose", value="jdg"),
        Pick(field="channel", value="paper"),
    ]:
        await feed(env, callback_update(UID, data.pack()))
    await feed(env, text_update(UID, "06.03.2026"))
    async with env[3]() as s:
        cases = await repo.list_cases(s, UID)
    assert cases and cases[0].dates()[Milestone.filed] == date(2026, 3, 6)


async def test_garbage_date_text_rejected(env):
    for data in [
        Nav(to="add"),
        Pick(field="voiv", value="mazowieckie"),
        Pick(field="purpose", value="jdg"),
        Pick(field="channel", value="paper"),
    ]:
        await feed(env, callback_update(UID, data.pack()))
    await feed(env, text_update(UID, "вчера вроде"))
    assert ru.MESSAGES["err_not_date"] in env[2].last().text


async def test_future_date_rejected(env):
    await drive_wizard(env, day=Day(y=2026, m=10, d=30))
    assert ru.MESSAGES["err_future"] in env[2].last().text
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 0


async def test_stale_case_callback_shows_menu(env):
    await feed(env, callback_update(UID, Nav(to="case", case_id=999).pack()))
    assert "Czekachiko" in env[2].last().text


async def test_unparseable_callback_shows_menu(env):
    await feed(env, callback_update(UID, "garbage:data"))
    assert "Czekachiko" in env[2].last().text


async def test_mark_milestone_from_case(env):
    await drive_wizard(env)
    async with env[3]() as s:
        case = (await repo.list_cases(s, UID))[0]
    for data in [
        Nav(to="case", case_id=case.id),
        Pick(field="milestone", value="fingerprints", case_id=case.id),
        Day(y=2026, m=10, d=29),
    ]:
        await feed(env, callback_update(UID, data.pack()))
    async with env[3]() as s:
        case = await repo.get_case(s, UID, case.id)
    assert case.dates()[Milestone.fingerprints] == date(2026, 10, 29)


async def seed_typical(session_factory):
    async with session_factory() as s:
        for i, days in enumerate([90, 100, 120, 150, 170, 190, 210, 240]):
            await repo.ensure_user(s, 1000 + i)
            c = await repo.create_case(
                s,
                1000 + i,
                Voivodeship.mazowieckie,
                Purpose.jdg,
                Channel.mos,
                date(2025, 1, 1),
                f"seed{i}",
            )
            await repo.set_milestone(
                s, c, Milestone.fingerprints, date.fromordinal(date(2025, 1, 1).toordinal() + days)
            )
        await s.commit()


async def test_outlier_confirm_flow(env):
    await seed_typical(env[3])
    await drive_wizard(env, day=Day(y=2024, m=12, d=1))
    async with env[3]() as s:
        case = (await repo.list_cases(s, UID))[0]
    await feed(
        env,
        callback_update(UID, Pick(field="milestone", value="fingerprints", case_id=case.id).pack()),
    )
    await feed(env, callback_update(UID, Day(y=2026, m=8, d=3).pack()))  # 610 days
    assert "610" in env[2].last().text
    await feed(env, callback_update(UID, Act(action="outlier_ok", case_id=case.id).pack()))
    async with env[3]() as s:
        case = await repo.get_case(s, UID, case.id)
        row = next(m for m in case.milestones if m.milestone == "fingerprints")
    assert row.confirmed_outlier is True


async def test_cancel_clears_wizard(env):
    await feed(env, callback_update(UID, Nav(to="add").pack()))
    await feed(env, text_update(UID, "/cancel"))
    await feed(env, callback_update(UID, Pick(field="purpose", value="jdg").pack()))
    assert "Czekachiko" in env[2].last().text


async def test_language_switch(env):
    await feed(env, callback_update(UID, Act(action="lang", value="en").pack()))
    await feed(env, text_update(UID, "/start"))
    assert any("estimates when" in t for t in env[2].texts())


async def test_delete_all_data(env):
    await drive_wizard(env)
    await feed(env, callback_update(UID, Act(action="del_all_yes").pack()))
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 0


async def test_throttle_drops_burst():
    clock = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5]).__next__
    mw = ThrottleMiddleware(rate=5, per=3.0, ban_after_per_min=40, ban_seconds=600, clock=clock)
    calls = 0

    async def handler(event, data):
        nonlocal calls
        calls += 1

    for _ in range(6):
        await mw(handler, None, {"event_from_user": type("U", (), {"id": 1})()})
    assert calls == 5


async def test_throttle_bans_flooder():
    t = [0.0]
    mw = ThrottleMiddleware(
        rate=1000, per=1.0, ban_after_per_min=40, ban_seconds=600, clock=lambda: t[0]
    )
    calls = 0

    async def handler(event, data):
        nonlocal calls
        calls += 1

    user = {"event_from_user": type("U", (), {"id": 1})()}
    for i in range(41):
        t[0] = i * 0.5
        await mw(handler, None, user)
    before = calls
    t[0] = 300
    await mw(handler, None, user)
    assert calls == before
    t[0] = 20.5 + 601
    await mw(handler, None, user)
    assert calls == before + 1


async def test_answer_failure_does_not_lose_data(env):
    env[2].fail_answer = True
    await drive_wizard(env)
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 1


async def test_double_tap_on_filed_date_creates_one_case_without_error(env):
    import asyncio

    for data in [
        Nav(to="add"),
        Pick(field="voiv", value="mazowieckie"),
        Pick(field="purpose", value="jdg"),
        Pick(field="channel", value="paper"),
    ]:
        await feed(env, callback_update(UID, data.pack()))
    tap = Day(y=2026, m=3, d=6).pack()
    await asyncio.gather(feed(env, callback_update(UID, tap)), feed(env, callback_update(UID, tap)))
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 1


def test_db_pool_covers_concurrency():
    from czekachiko.db.session import MAX_OVERFLOW, POOL_SIZE
    from czekachiko.middlewares import CONCURRENCY

    # each in-flight update may hold its own session plus one FSM-storage session
    assert CONCURRENCY * 2 <= POOL_SIZE + MAX_OVERFLOW
