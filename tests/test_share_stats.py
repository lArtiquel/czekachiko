from datetime import date

import pytest
from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, Update

from czekachiko import share
from czekachiko.app import build_dispatcher
from czekachiko.config import DEFAULT_WEBAPP_URL
from czekachiko.db import repo
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.locales import en, ru
from czekachiko.ui.keyboards import Act, Nav, Pick
from tests.fakes import _ids, _user, callback_update, make_bot, text_update

UID = 548


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory,
        clock=lambda: date(2026, 10, 29),
        admin_tg_id=None,
        calendar_url=None,
        throttle=False,
        ephemeral_delay=0,
    )
    async with session_factory() as s:
        await repo.ensure_user(s, 1)
        c = await repo.create_case(
            s, 1, Voivodeship.mazowieckie, Purpose.jdg, Channel.paper, date(2026, 3, 6), "seed"
        )
        await repo.set_milestone(s, c, Milestone.fingerprints, date(2026, 10, 29))
        await s.commit()
    return dp, bot, tg, session_factory


async def feed(env, update):
    await env[0].feed_update(env[1], update)


def inline_update(query: str) -> Update:
    iq = InlineQuery(id=str(next(_ids)), from_user=_user(UID), query=query, offset="")
    return Update(update_id=next(_ids), inline_query=iq)


def answers(tg) -> list[AnswerInlineQuery]:
    return [c for c in tg.calls if isinstance(c, AnswerInlineQuery)]


def test_alias_matching():
    V = Voivodeship
    assert share.match_voivodeships("варшава") == [V.mazowieckie]
    assert share.match_voivodeships("Warszawa") == [V.mazowieckie]
    assert share.match_voivodeships("maz") == [V.mazowieckie]
    assert share.match_voivodeships("kraków") == [V.malopolskie]
    assert share.match_voivodeships("wroclaw") == [V.dolnoslaskie]
    assert share.match_voivodeships("") == []


def test_code_roundtrip():
    code = share.encode("jdg", [Voivodeship.mazowieckie, Voivodeship.malopolskie])
    assert share.decode(code) == ("jdg", [Voivodeship.mazowieckie, Voivodeship.malopolskie])
    assert share.decode("garbage") is None
    assert share.decode("s:jdg:99") is None


async def test_compare_picker_and_send_button(env):
    for data in [
        Nav(to="compare"),
        Pick(field="cmp_purpose", value="jdg"),
        Act(action="cmp_toggle", value="mazowieckie"),
        Act(action="cmp_toggle", value="malopolskie"),
        Act(action="cmp_show"),
    ]:
        await feed(env, callback_update(UID, data.pack()))
    last = env[2].last()
    assert "Mazowieckie" in last.text and "Małopolskie" in last.text
    send = [
        b
        for row in last.reply_markup.inline_keyboard
        for b in row
        if b.switch_inline_query_chosen_chat
    ]
    assert send and share.decode(send[0].switch_inline_query_chosen_chat.query) == (
        "jdg",
        [Voivodeship.mazowieckie, Voivodeship.malopolskie],
    )


async def test_inline_code_returns_card(env):
    code = share.encode("jdg", [Voivodeship.mazowieckie])
    await feed(env, inline_update(code))
    (a,) = answers(env[2])
    assert len(a.results) == 1
    text = a.results[0].input_message_content.message_text
    assert "Mazowieckie" in text and "(дел: 1)" in text
    assert a.results[0].reply_markup.inline_keyboard[0][0].url == "https://t.me/czekachiko_bot"


async def test_inline_empty_query_lists_cards_and_an_app_button(env):
    await feed(env, inline_update(""))
    (a,) = answers(env[2])
    assert a.results
    assert a.button.text == ru.MESSAGES["inline_open_app"] == "📱 Выбрать в приложении"
    assert a.button.web_app.url == DEFAULT_WEBAPP_URL + "#/stats"
    assert a.button.start_parameter is None
    assert en.MESSAGES["inline_open_app"] == "📱 Choose in the app"


async def test_inline_app_button_uses_the_configured_url(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory,
        clock=lambda: date(2026, 10, 29),
        throttle=False,
        webapp_url="https://example.org/a/",
    )
    await dp.feed_update(bot, inline_update("варшава"))
    (a,) = answers(tg)
    assert a.button.web_app.url == "https://example.org/a/#/stats"


async def test_inline_alias_query(env):
    await feed(env, inline_update("варшава"))
    (a,) = answers(env[2])
    assert all("Mazowieckie" in r.title for r in a.results)


async def test_start_pick_opens_compare_picker(env):
    await feed(env, text_update(UID, "/start pick"))
    assert ru.MESSAGES["cmp_pick_purpose"] in env[2].last().text


async def test_compare_limit(env):
    await feed(env, callback_update(UID, Nav(to="compare").pack()))
    await feed(env, callback_update(UID, Pick(field="cmp_purpose", value="jdg").pack()))
    for v in list(Voivodeship)[:7]:
        await feed(env, callback_update(UID, Act(action="cmp_toggle", value=v.value).pack()))
    data = await env[0].storage.get_data(
        __import__("aiogram").fsm.storage.base.StorageKey(bot_id=42, chat_id=UID, user_id=UID)
    )
    assert len(data["cmp"]) == share.MAX_COMPARE


async def owner_case_id(env):
    async with env[3]() as s:
        await repo.ensure_user(s, UID)
        c = await repo.create_case(
            s, UID, Voivodeship.mazowieckie, Purpose.jdg, Channel.paper, date(2026, 3, 6), "mine"
        )
        await repo.set_milestone(s, c, Milestone.fingerprints, date(2026, 10, 29))
        await s.commit()
        return c.id


def switch_queries(markup):
    return [
        b.switch_inline_query_chosen_chat.query
        for row in markup.inline_keyboard
        for b in row
        if b.switch_inline_query_chosen_chat
    ]


async def test_case_view_has_send_button(env):
    cid = await owner_case_id(env)
    await feed(env, callback_update(UID, Nav(to="case", case_id=cid).pack()))
    assert switch_queries(env[2].last().reply_markup) == [f"c:{cid}"]


async def test_inline_case_card_for_owner(env):
    cid = await owner_case_id(env)
    await feed(env, inline_update(f"c:{cid}"))
    (a,) = answers(env[2])
    text = a.results[0].input_message_content.message_text
    assert "Mazowieckie" in text and "29.10.2026" in text and str(UID) not in text


async def test_inline_case_card_refused_for_others(env):
    async with env[3]() as s:
        c = await repo.get_case(s, 1, 1)  # the seeded case belongs to user 1, not UID
    await feed(env, inline_update(f"c:{c.id}"))
    (a,) = answers(env[2])
    assert a.results == []


async def test_stats_view_has_send_button(env):
    await feed(
        env, callback_update(UID, Pick(field="stats_purpose", value="mazowieckie|jdg").pack())
    )
    assert switch_queries(env[2].last().reply_markup) == [
        share.encode("jdg", [Voivodeship.mazowieckie])
    ]
