from datetime import date

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageText,
    SendMessage,
    SetMyCommands,
)
from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy import func, select

from czekachiko.__main__ import set_commands
from czekachiko.app import build_dispatcher
from czekachiko.config import DEFAULT_WEBAPP_URL
from czekachiko.db import repo
from czekachiko.db.models import Feedback
from czekachiko.domain import Channel, Purpose, Voivodeship
from czekachiko.locales import en, ru
from czekachiko.middlewares import ThrottleMiddleware
from tests.fakes import callback_update, make_bot, text_update

UID = 548
TODAY = date(2026, 10, 29)


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(session_factory, clock=lambda: TODAY, admin_tg_id=None, throttle=False)
    yield dp, bot, tg, session_factory


async def feed(env, update):
    dp, bot, tg, _ = env
    await dp.feed_update(bot, update)


def _deleted(tg):
    return [c.message_id for c in tg.calls if isinstance(c, DeleteMessage)]


def launcher_url(message) -> str:
    ((button,),) = message.reply_markup.inline_keyboard
    return button.web_app.url


# --- /start ------------------------------------------------------------------------------


async def test_start_shows_one_short_message_with_the_mini_app_button(env):
    await feed(env, text_update(UID, "/start"))
    tg = env[2]
    visible = [
        c for i, c in enumerate(tg.calls) if i in tg.sent_ids and tg.sent_ids[i] not in _deleted(tg)
    ]
    assert len(visible) == 1
    assert visible[0].text == ru.MESSAGES["menu_title"] and len(visible[0].text) < 400
    ((button,),) = visible[0].reply_markup.inline_keyboard
    assert button.text == "🚀 Открыть Czekachiko"
    assert button.web_app.url == DEFAULT_WEBAPP_URL


async def test_start_sends_persistent_reply_menu(env):
    await feed(env, text_update(UID, "/start"))
    kbs = [c.reply_markup for c in env[2].calls if isinstance(c, SendMessage)]
    reply = [k for k in kbs if isinstance(k, ReplyKeyboardMarkup)]
    assert reply and reply[0].is_persistent and reply[0].resize_keyboard
    (app, write), *rest = reply[0].keyboard
    assert rest == []
    assert app.text == ru.MESSAGES["btn_open_app"] == "🚀 Открыть приложение"
    # Keyboard-button Mini Apps get no initData, so this button answers with the inline launcher.
    assert app.web_app is None
    assert write.text == ru.MESSAGES["btn_feedback"] == "✉️ Написать нам"
    assert write.web_app is None


async def test_start_uses_the_configured_mini_app_url(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory, clock=lambda: TODAY, throttle=False, webapp_url="https://example.org/a/"
    )
    await dp.feed_update(bot, text_update(UID, "/start"))
    markups = [c.reply_markup for c in tg.calls if getattr(c, "reply_markup", None)]
    urls = {
        b.web_app.url
        for m in markups
        for row in getattr(m, "inline_keyboard", None) or m.keyboard
        for b in row
        if b.web_app
    }
    assert urls == {"https://example.org/a/"}


async def test_start_in_english(env):
    async with env[3]() as s:
        await repo.set_lang(s, UID, "en")
        await s.commit()
    await feed(env, text_update(UID, "/start"))
    ((button,),) = env[2].last().reply_markup.inline_keyboard
    assert button.text == en.MESSAGES["btn_open_webapp"] == "🚀 Open Czekachiko"
    reply = [
        c.reply_markup
        for c in env[2].calls
        if isinstance(c, SendMessage) and isinstance(c.reply_markup, ReplyKeyboardMarkup)
    ]
    labels = {b.text for row in reply[-1].keyboard for b in row}
    assert labels == {en.MESSAGES["btn_open_app"], en.MESSAGES["btn_feedback"]}


@pytest.mark.parametrize("command", ["/start pick", "/start anything-else"])
async def test_deep_links_show_the_launcher(env, command):
    await feed(env, text_update(UID, command))
    assert env[2].last().text == ru.MESSAGES["menu_title"]
    assert launcher_url(env[2].last()) == DEFAULT_WEBAPP_URL


async def test_keyboard_open_app_replies_with_inline_launcher(env):
    """Also what clients without Mini App support get: the label arrives as text."""
    for label in (ru.MESSAGES["btn_open_app"], en.MESSAGES["btn_open_app"]):
        await feed(env, text_update(UID, label))
        assert launcher_url(env[2].last()) == DEFAULT_WEBAPP_URL


async def test_launcher_replaces_the_previous_message(env):
    await feed(env, text_update(UID, "/start"))
    first_id = env[2].last_sent_id()
    upd = text_update(UID, ru.MESSAGES["btn_open_app"])
    await feed(env, upd)
    deleted = _deleted(env[2])
    assert upd.message.message_id in deleted  # the user's own button press
    assert first_id in deleted  # the previous bot message


async def test_only_start_is_in_the_command_menu():
    bot, tg = make_bot()
    await set_commands(bot)
    calls = [c for c in tg.calls if isinstance(c, SetMyCommands)]
    assert [c.language_code for c in calls] == [None, "ru", "en"]
    for call in calls:
        assert [c.command for c in call.commands] == ["start"]
    assert [c.commands[0].description for c in calls] == [
        ru.MESSAGES["cmd_start"],
        ru.MESSAGES["cmd_start"],
        en.MESSAGES["cmd_start"],
    ]
    assert not ru.MESSAGES["cmd_start"][0].isalnum() and not en.MESSAGES["cmd_start"][0].isalnum()


# --- everything the bot no longer handles ------------------------------------------------


async def seed_case(env):
    async with env[3]() as s:
        await repo.ensure_user(s, UID)
        c = await repo.create_case(
            s, UID, Voivodeship.mazowieckie, Purpose.jdg, Channel.post, date(2026, 3, 6), "t"
        )
        await s.commit()
        return c.id


@pytest.mark.parametrize(
    "data",
    ["n:case:{cid}", "n:menu:0", "a:del_case_yes:{cid}:", "a:del_all_yes:0:", "d:2026:3:6", "zzz"],
)
async def test_old_buttons_answer_with_a_toast_and_change_nothing(env, data):
    cid = await seed_case(env)
    await feed(env, callback_update(UID, data.format(cid=cid)))
    calls = env[2].calls
    assert [c.text for c in calls if isinstance(c, AnswerCallbackQuery)] == [
        ru.MESSAGES["stale_button"]
    ]
    assert not [c for c in calls if isinstance(c, SendMessage | EditMessageText)]
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 1


async def test_old_button_survives_a_failed_answer(env):
    env[2].fail_answer = True
    await feed(env, callback_update(UID, "n:case:5"))


async def test_unknown_text_gets_one_line_and_the_launcher(env):
    await feed(env, text_update(UID, "/start"))
    before = len(env[2].texts())
    upd = text_update(UID, "привет, когда будет decyzja?")
    await feed(env, upd)
    assert len(env[2].texts()) == before + 1
    assert env[2].last().text == ru.MESSAGES["unknown_message"]
    assert launcher_url(env[2].last()) == DEFAULT_WEBAPP_URL
    assert upd.message.message_id in _deleted(env[2])
    async with env[3]() as s:  # free text is never stored
        assert await s.scalar(select(func.count()).select_from(Feedback)) == 0


async def test_labels_of_the_old_keyboard_get_the_launcher(env):
    await feed(env, text_update(UID, "📂 Мои дела"))
    assert env[2].last().text == ru.MESSAGES["unknown_message"]


async def test_state_of_a_removed_flow_is_dropped(env):
    """A user left mid-wizard before the update: their next message creates nothing."""
    key = StorageKey(bot_id=42, chat_id=UID, user_id=UID)
    storage = env[0].storage
    await storage.set_state(key, "AddCase:filed")
    await storage.set_data(key, {"voiv": "mazowieckie", "purpose": "jdg", "channel": "paper"})
    await feed(env, text_update(UID, "06.03.2026"))
    assert env[2].last().text == ru.MESSAGES["unknown_message"]
    assert await storage.get_state(key) is None
    async with env[3]() as s:
        assert await repo.count_cases(s, UID) == 0


# --- middlewares -------------------------------------------------------------------------


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


def test_db_pool_covers_concurrency():
    from czekachiko.db.session import MAX_OVERFLOW, POOL_SIZE
    from czekachiko.middlewares import CONCURRENCY

    # each in-flight update may hold its own session plus one FSM-storage session
    assert CONCURRENCY * 2 <= POOL_SIZE + MAX_OVERFLOW
