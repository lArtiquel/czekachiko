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


async def test_start_shows_menu_without_privacy(env):
    await feed(env, text_update(UID, "/start"))
    texts = env[2].texts()
    assert any("Czekachiko" in t for t in texts)
    assert not any(ru.MESSAGES["privacy"][:20] in t for t in texts)


async def test_help_includes_privacy(env):
    await feed(env, text_update(UID, ru.MESSAGES["btn_help"]))
    assert ru.MESSAGES["privacy"] in env[2].last().text


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
    assert ru.MESSAGES["err_use_buttons"] in env[2].last().text
    assert ru.MESSAGES["ask_voiv"] in env[2].last().text  # stays on the same wizard step
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


async def test_start_sends_persistent_reply_menu(env):
    from aiogram.methods import SendMessage
    from aiogram.types import ReplyKeyboardMarkup

    await feed(env, text_update(UID, "/start"))
    kbs = [c.reply_markup for c in env[2].calls if isinstance(c, SendMessage)]
    reply = [k for k in kbs if isinstance(k, ReplyKeyboardMarkup)]
    assert reply and reply[0].is_persistent and reply[0].resize_keyboard
    labels = {b.text for row in reply[0].keyboard for b in row}
    assert ru.MESSAGES["btn_cases"] in labels and ru.MESSAGES["btn_add"] in labels


async def test_reply_menu_button_opens_cases(env):
    await drive_wizard(env)
    await feed(env, text_update(UID, ru.MESSAGES["btn_cases"]))
    assert ru.MESSAGES["cases_title"] in env[2].last().text


async def test_reply_menu_button_leaves_date_picker(env):
    for data in [
        Nav(to="add"),
        Pick(field="voiv", value="mazowieckie"),
        Pick(field="purpose", value="jdg"),
        Pick(field="channel", value="paper"),
    ]:
        await feed(env, callback_update(UID, data.pack()))
    await feed(env, text_update(UID, ru.MESSAGES["btn_stats"]))
    assert ru.MESSAGES["stats_pick_voiv"] in env[2].last().text


async def test_reply_menu_add_starts_wizard(env):
    await feed(env, text_update(UID, ru.MESSAGES["btn_add"]))
    assert ru.MESSAGES["ask_voiv"] in env[2].last().text


async def test_language_switch_resends_reply_menu(env):
    from aiogram.methods import SendMessage
    from aiogram.types import ReplyKeyboardMarkup

    from czekachiko.locales import en

    await feed(env, callback_update(UID, Act(action="lang", value="en").pack()))
    reply = [
        c.reply_markup
        for c in env[2].calls
        if isinstance(c, SendMessage) and isinstance(c.reply_markup, ReplyKeyboardMarkup)
    ]
    assert reply and en.MESSAGES["btn_cases"] in {b.text for row in reply[-1].keyboard for b in row}


def test_command_descriptions_have_emoji():
    from czekachiko.locales import en

    for loc in (ru, en):
        for c in ["start", "cases", "add", "stats", "calendar", "settings", "help", "cancel"]:
            assert not loc.MESSAGES[f"cmd_{c}"][0].isalnum(), c


async def test_start_is_one_short_message(env):
    await feed(env, text_update(UID, "/start"))
    texts = env[2].texts()
    assert len(texts) == 1
    assert len(texts[0]) < 400
    assert "Czekachiko" in texts[0] and "Telegram ID" not in texts[0]


async def test_reply_menu_share_button(env):
    await feed(env, text_update(UID, ru.MESSAGES["btn_share"]))
    assert env[2].last().text == ru.MESSAGES["share_prompt"]
    kb = env[2].last().reply_markup
    assert any(b.url and "t.me/share/url" in b.url for row in kb.inline_keyboard for b in row)


def _deleted(tg):
    from aiogram.methods import DeleteMessage

    return [c.message_id for c in tg.calls if isinstance(c, DeleteMessage)]


async def test_menu_button_cleans_up_chat(env):
    from aiogram.methods import SendMessage

    await feed(env, text_update(UID, "/start"))
    first_screen_id = env[2].last_sent_id()
    upd = text_update(UID, ru.MESSAGES["btn_cases"])
    await feed(env, upd)
    deleted = _deleted(env[2])
    assert upd.message.message_id in deleted  # the user's own "📂 Мои дела" message
    assert first_screen_id in deleted  # the previous bot screen
    assert ru.MESSAGES["cases_title"] in env[2].last().text
    assert any(isinstance(c, SendMessage) for c in env[2].calls)


async def test_language_switch_shows_toast_and_leaves_no_message(env):
    from aiogram.methods import AnswerCallbackQuery, SendMessage
    from aiogram.types import ReplyKeyboardMarkup

    from czekachiko.locales import en

    await feed(env, callback_update(UID, Act(action="lang", value="en").pack()))
    toasts = [c.text for c in env[2].calls if isinstance(c, AnswerCallbackQuery) and c.text]
    assert toasts == [en.MESSAGES["lang_changed"]]
    sent = [
        c
        for c in env[2].calls
        if isinstance(c, SendMessage) and isinstance(c.reply_markup, ReplyKeyboardMarkup)
    ]
    assert sent  # keyboard refreshed in the new language...
    assert env[2].sent_ids[env[2].calls.index(sent[-1])] in _deleted(env[2])  # ...and removed


async def test_stray_text_is_one_screen(env):
    await feed(env, text_update(UID, "/start"))
    before = len(env[2].texts())
    await feed(env, text_update(UID, "привет"))
    assert len(env[2].texts()) == before + 1
    assert ru.MESSAGES["err_use_buttons"] in env[2].last().text
