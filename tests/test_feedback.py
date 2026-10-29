from datetime import date

import pytest
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update
from sqlalchemy import select

from czekachiko.app import build_dispatcher
from czekachiko.db.models import Feedback
from czekachiko.locales import ru
from czekachiko.ui.keyboards import Nav
from tests.fakes import NOW, _ids, _user, callback_update, make_bot, text_update

UID, ADMIN = 548, 777


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory,
        clock=lambda: date(2026, 10, 29),
        admin_tg_id=ADMIN,
        calendar_url=None,
        throttle=False,
        ephemeral_delay=0,
    )
    return dp, bot, tg, session_factory


async def feed(env, update):
    await env[0].feed_update(env[1], update)


def sends_to(tg, chat_id):
    return [c for c in tg.calls if isinstance(c, SendMessage) and c.chat_id == chat_id]


def admin_reply(text: str, reply_to_id: int) -> Update:
    original = Message(
        message_id=reply_to_id, date=NOW, chat=Chat(id=ADMIN, type="private"), text="x"
    )
    msg = Message(
        message_id=next(_ids),
        date=NOW,
        chat=Chat(id=ADMIN, type="private"),
        from_user=_user(ADMIN),
        text=text,
        reply_to_message=original,
    )
    return Update(update_id=next(_ids), message=msg)


async def send_feedback(env, text="Бот супер, но добавьте Łódź 🙏"):
    await feed(env, callback_update(UID, Nav(to="feedback").pack()))
    await feed(env, text_update(UID, text))


async def test_feedback_delivered_to_admin_and_confirmed(env):
    await send_feedback(env)
    to_admin = sends_to(env[2], ADMIN)
    assert len(to_admin) == 1 and "Łódź" in to_admin[0].text
    assert to_admin[0].parse_mode is None  # user text is never parsed as HTML
    assert any(ru.MESSAGES["feedback_sent"] in t for t in env[2].texts())
    async with env[3]() as s:
        row = (await s.scalars(select(Feedback))).one()
    assert row.tg_id == UID and row.direction == "in" and row.admin_msg_id


async def test_admin_reply_goes_only_to_author(env):
    await send_feedback(env)
    async with env[3]() as s:
        row = (await s.scalars(select(Feedback))).one()
    await feed(env, admin_reply("Спасибо, добавим!", row.admin_msg_id))
    to_user = sends_to(env[2], UID)
    assert any("Спасибо, добавим!" in m.text for m in to_user)


async def test_reply_from_non_admin_is_ignored(env):
    await send_feedback(env)
    async with env[3]() as s:
        row = (await s.scalars(select(Feedback))).one()
    before = len(sends_to(env[2], UID))
    update = admin_reply("hijack", row.admin_msg_id)
    update.message.from_user.id  # noqa: B018
    stranger = update.model_copy(
        update={
            "message": update.message.model_copy(
                update={"from_user": _user(999), "chat": Chat(id=999, type="private")}
            )
        }
    )
    await feed(env, stranger)
    assert not any("hijack" in m.text for m in sends_to(env[2], UID)[before:])


async def test_feedback_rate_limited(env):
    for i in range(6):
        await send_feedback(env, f"сообщение {i}")
    assert len(sends_to(env[2], ADMIN)) == 5
    assert ru.MESSAGES["feedback_limit"] in env[2].last().text


async def test_feedback_too_long_rejected(env):
    await send_feedback(env, "a" * 1001)
    assert sends_to(env[2], ADMIN) == []
    assert ru.MESSAGES["feedback_too_long"] in env[2].last().text
