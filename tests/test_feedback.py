from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    DeleteMessage,
    EditMessageText,
    SendMessage,
    SetMessageReaction,
)
from aiogram.types import Chat, Location, Message, Update
from sqlalchemy import select

from czekachiko.app import build_dispatcher
from czekachiko.config import DEFAULT_WEBAPP_URL
from czekachiko.db import repo
from czekachiko.db.models import Feedback
from czekachiko.handlers import feedback as fb
from czekachiko.keyboards import FEEDBACK_CANCEL
from czekachiko.locales import en, ru
from tests.fakes import NOW, _ids, _user, callback_update, make_bot, photo_update, text_update

UID, ADMIN = 548, 777


@pytest.fixture
async def env(session_factory):
    bot, tg = make_bot()
    dp = build_dispatcher(
        session_factory,
        clock=lambda: date(2026, 10, 29),
        admin_tg_id=ADMIN,
        throttle=False,
        ephemeral_delay=0,
    )
    return dp, bot, tg, session_factory


async def feed(env, update):
    await env[0].feed_update(env[1], update)


def sends_to(tg, chat_id):
    return [c for c in tg.calls if isinstance(c, SendMessage) and c.chat_id == chat_id]


def copies_to(tg, chat_id):
    return [c for c in tg.calls if isinstance(c, CopyMessage) and c.chat_id == chat_id]


def deleted(tg):
    return {c.message_id for c in tg.calls if isinstance(c, DeleteMessage)}


def reactions(tg, chat_id):
    return [c for c in tg.calls if isinstance(c, SetMessageReaction) and c.chat_id == chat_id]


def admin_message(text: str, reply_to_id: int | None = None) -> Update:
    original = (
        Message(message_id=reply_to_id, date=NOW, chat=Chat(id=ADMIN, type="private"), text="x")
        if reply_to_id
        else None
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


def admin_reply(text: str, reply_to_id: int) -> Update:
    return admin_message(text, reply_to_id)


async def open_chat(env):
    await feed(env, text_update(UID, ru.MESSAGES["btn_feedback"]))


async def send_feedback(env, text="Бот супер, но добавьте Łódź 🙏"):
    await open_chat(env)
    await feed(env, text_update(UID, text))


async def rows(env) -> list[Feedback]:
    async with env[3]() as s:
        return list((await s.scalars(select(Feedback).order_by(Feedback.id))).all())


# --- the user's side -------------------------------------------------------------------


async def test_feedback_delivered_to_admin_and_stored(env):
    await send_feedback(env)
    to_admin = sends_to(env[2], ADMIN)
    assert len(to_admin) == 1 and "Łódź" in to_admin[0].text
    assert to_admin[0].parse_mode is None  # user text is never parsed as HTML
    (row,) = await rows(env)
    assert row.tg_id == UID and row.direction == "in" and row.admin_msg_id


async def test_open_chat_forwards_every_message_until_closed(env):
    await open_chat(env)
    for text in ("первое", "второе", "третье"):
        await feed(env, text_update(UID, text))
    assert [m.text.split("\n\n", 1)[1] for m in sends_to(env[2], ADMIN)] == [
        "первое",
        "второе",
        "третье",
    ]
    assert len(await rows(env)) == 3


async def test_users_messages_stay_in_their_chat_and_get_a_reaction(env):
    await open_chat(env)
    update = text_update(UID, "останься в истории")
    await feed(env, update)
    assert update.message.message_id not in deleted(env[2])
    (reaction,) = reactions(env[2], UID)
    assert reaction.message_id == update.message.message_id


async def test_no_launcher_after_each_message_while_the_chat_is_open(env):
    await send_feedback(env)
    assert not [m for m in sends_to(env[2], UID) if m.text == ru.MESSAGES["menu_title"]]


async def test_photo_is_copied_to_admin_with_a_header_and_stored(env):
    await open_chat(env)
    await feed(env, photo_update(UID, caption="вот скрин"))
    (copy,) = copies_to(env[2], ADMIN)
    assert copy.from_chat_id == UID and copy.parse_mode is None
    assert copy.caption.startswith("✉️") and copy.caption.endswith("вот скрин")
    (row,) = await rows(env)
    assert row.media == "photo" and row.text == "вот скрин" and row.admin_msg_id


async def test_unsupported_content_keeps_the_chat_open(env):
    await open_chat(env)
    msg = Message(
        message_id=next(_ids),
        date=NOW,
        chat=Chat(id=UID, type="private"),
        from_user=_user(UID),
        location=Location(latitude=52.2, longitude=21.0),
    )
    await feed(env, Update(update_id=next(_ids), message=msg))
    assert ru.MESSAGES["feedback_text_only"] in env[2].last().text
    await feed(env, text_update(UID, "а теперь текстом"))
    assert len(sends_to(env[2], ADMIN)) == 1


async def test_feedback_rate_limited(env):
    await open_chat(env)
    for i in range(fb.PER_HOUR + 1):
        await feed(env, text_update(UID, f"сообщение {i}"))
    assert len(sends_to(env[2], ADMIN)) == fb.PER_HOUR
    assert ru.MESSAGES["feedback_limit"] in env[2].last().text


async def test_feedback_too_long_rejected(env):
    await send_feedback(env, "a" * 1001)
    assert sends_to(env[2], ADMIN) == []
    assert ru.MESSAGES["feedback_too_long"] in env[2].last().text


async def test_deleting_data_does_not_reset_feedback_limit(env):
    await open_chat(env)
    for i in range(fb.PER_HOUR):
        await feed(env, text_update(UID, f"сообщение {i}"))
    async with env[3]() as s:  # what DELETE /api/me does
        await repo.delete_user(s, UID)
        await s.commit()
    await send_feedback(env, "ещё одно после удаления")
    assert len(sends_to(env[2], ADMIN)) == fb.PER_HOUR
    assert ru.MESSAGES["feedback_limit"] in env[2].last().text


async def test_start_feedback_deep_link_opens_the_chat(env):
    await feed(env, text_update(UID, "/start feedback"))
    assert ru.MESSAGES["feedback_prompt"] in env[2].last().text
    await feed(env, text_update(UID, "Привет из мини-приложения"))
    assert any("Привет из мини-приложения" in m.text for m in sends_to(env[2], ADMIN))


@pytest.mark.parametrize("label", [ru.MESSAGES["btn_feedback"], en.MESSAGES["btn_feedback"]])
async def test_keyboard_button_opens_the_chat_with_a_close_button(env, label):
    await feed(env, text_update(UID, label))
    last = env[2].last()
    assert last.text == ru.MESSAGES["feedback_prompt"]
    ((button,),) = last.reply_markup.inline_keyboard
    assert button.text == ru.MESSAGES["btn_close_support"]
    assert button.callback_data == FEEDBACK_CANCEL


async def test_closing_stops_forwarding_and_shows_the_launcher(env):
    await open_chat(env)
    await feed(env, callback_update(UID, FEEDBACK_CANCEL))
    edit = env[2].last()
    assert isinstance(edit, EditMessageText) and edit.text == ru.MESSAGES["feedback_closed"]
    ((button,),) = edit.reply_markup.inline_keyboard
    assert button.web_app.url == DEFAULT_WEBAPP_URL
    await feed(env, text_update(UID, "это уже не обратная связь"))
    assert sends_to(env[2], ADMIN) == []
    assert env[2].last().text == ru.MESSAGES["unknown_message"]


async def test_chat_closes_itself_after_a_week_of_silence(env):
    await send_feedback(env, "первое")
    key = StorageKey(bot_id=env[1].id, chat_id=UID, user_id=UID)
    stale = (datetime.now(UTC) - fb.IDLE_CLOSE - timedelta(minutes=1)).isoformat()
    await env[0].storage.update_data(key, {"since": stale})
    await feed(env, text_update(UID, "через восемь дней"))
    assert len(sends_to(env[2], ADMIN)) == 1
    assert env[2].last().text == ru.MESSAGES["unknown_message"]


async def test_old_menu_button_on_the_prompt_leaves_the_flow(env):
    """The old prompt also had «🏠 Меню» (n:menu:0); it must not open any old screen."""
    await feed(env, text_update(UID, "/start feedback"))
    await feed(env, callback_update(UID, "n:menu:0"))
    toasts = [c.text for c in env[2].calls if isinstance(c, AnswerCallbackQuery)]
    assert toasts == [ru.MESSAGES["stale_button"]]
    assert env[2].last().text == ru.MESSAGES["feedback_prompt"]  # nothing new was shown
    await feed(env, text_update(UID, "случайный текст"))
    assert sends_to(env[2], ADMIN) == []


# --- the maintainer's side -------------------------------------------------------------


async def test_admin_reply_goes_only_to_author_and_is_stored(env):
    await send_feedback(env)
    (incoming,) = await rows(env)
    reply = admin_reply("Спасибо, добавим!", incoming.admin_msg_id)
    await feed(env, reply)
    (to_user,) = [m for m in sends_to(env[2], UID) if "Спасибо, добавим!" in m.text]
    ((close,),) = to_user.reply_markup.inline_keyboard
    assert close.callback_data == fb.FEEDBACK_CLOSE
    out = (await rows(env))[-1]
    assert (out.direction, out.tg_id, out.text) == ("out", UID, "Спасибо, добавим!")
    assert out.admin_msg_id == reply.message.message_id
    # Delivery is confirmed with a reaction on the reply, which stays in the admin's chat.
    assert [r.message_id for r in reactions(env[2], ADMIN)] == [reply.message.message_id]
    assert reply.message.message_id not in deleted(env[2])


async def test_admin_can_reply_to_any_message_of_the_thread(env):
    await open_chat(env)
    await feed(env, text_update(UID, "первое"))
    await feed(env, text_update(UID, "второе"))
    second = (await rows(env))[-1]
    await feed(env, admin_reply("ответ на второе", second.admin_msg_id))
    first_answer = (await rows(env))[-1]
    await feed(env, admin_reply("и ещё", first_answer.admin_msg_id))  # reply to own reply
    texts = [m.text for m in sends_to(env[2], UID)]
    assert any("ответ на второе" in t for t in texts) and any("и ещё" in t for t in texts)


async def test_admin_reply_reopens_a_closed_chat(env):
    await send_feedback(env)
    await feed(env, callback_update(UID, FEEDBACK_CANCEL))
    (incoming,) = await rows(env)
    await feed(env, admin_reply("Уточни, пожалуйста, воеводство", incoming.admin_msg_id))
    await feed(env, text_update(UID, "Mazowieckie"))
    assert any("Mazowieckie" in m.text for m in sends_to(env[2], ADMIN))


async def test_admin_photo_reply_is_copied_and_stored(env):
    await send_feedback(env)
    (incoming,) = await rows(env)
    original = Message(
        message_id=incoming.admin_msg_id, date=NOW, chat=Chat(id=ADMIN, type="private"), text="x"
    )
    await feed(env, photo_update(ADMIN, caption="вот так", reply_to=original))
    (copy,) = copies_to(env[2], UID)
    assert copy.from_chat_id == ADMIN and copy.caption.endswith("вот так")
    out = (await rows(env))[-1]
    assert (out.direction, out.media, out.text) == ("out", "photo", "вот так")


async def test_undelivered_reply_is_reported_and_not_stored(env):
    await send_feedback(env)
    (incoming,) = await rows(env)
    env[2].blocked.add(UID)
    await feed(env, admin_reply("алло", incoming.admin_msg_id))
    assert ru.MESSAGES["feedback_undelivered"] in env[2].last().text
    assert len(await rows(env)) == 1


async def test_admin_message_without_reply_gets_a_hint_and_stays(env):
    update = admin_message("кому это?")
    await feed(env, update)
    assert env[2].last().text == ru.MESSAGES["feedback_admin_hint"]
    assert update.message.message_id not in deleted(env[2])


async def test_reply_from_non_admin_is_ignored(env):
    await send_feedback(env)
    (incoming,) = await rows(env)
    before = len(sends_to(env[2], UID))
    update = admin_reply("hijack", incoming.admin_msg_id)
    stranger = update.model_copy(
        update={
            "message": update.message.model_copy(
                update={"from_user": _user(999), "chat": Chat(id=999, type="private")}
            )
        }
    )
    await feed(env, stranger)
    assert not any("hijack" in m.text for m in sends_to(env[2], UID)[before:])


async def test_history_shows_the_thread_to_the_admin_only(env):
    await send_feedback(env, "вопрос")
    (incoming,) = await rows(env)
    await feed(env, admin_reply("ответ", incoming.admin_msg_id))
    await feed(env, admin_message(f"/history {UID}"))
    history = env[2].last().text
    assert "вопрос" in history and "ответ" in history
    assert history.index("вопрос") < history.index("ответ")
    await feed(env, text_update(999, f"/history {UID}"))
    assert "вопрос" not in env[2].last().text


async def test_user_id_in_the_admin_header_opens_the_user(env):
    await send_feedback(env, "привет")
    (to_admin,) = sends_to(env[2], ADMIN)
    (mention,) = to_admin.entities
    assert mention.type == "text_mention" and mention.user.id == UID
    # Offsets count UTF-16 code units, as Telegram does (✉️ is two of them).
    units = to_admin.text.encode("utf-16-le")
    shown = units[mention.offset * 2 : (mention.offset + mention.length) * 2]
    assert shown.decode("utf-16-le") == str(UID)


async def test_user_id_in_a_media_caption_opens_the_user(env):
    await open_chat(env)
    await feed(env, photo_update(UID, caption="скрин"))
    (copy,) = copies_to(env[2], ADMIN)
    (mention,) = copy.caption_entities
    assert mention.type == "text_mention" and mention.user.id == UID
