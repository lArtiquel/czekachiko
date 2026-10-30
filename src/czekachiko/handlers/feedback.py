"""The support chat: a user ↔ maintainer thread that stays open until the user closes it.

- «✉️ Написать нам» (or `/start feedback` from the Mini App) opens the chat. While it is
  open, every text, photo, file or video the user sends is copied to the maintainer and
  stored. Nothing is deleted from either chat, so both keep the whole conversation.
- The maintainer answers by replying to any message of the thread (the user's or their own
  earlier answer). The answer goes to that user only, is stored, and reopens the chat so the
  user can answer back. Delivery is confirmed with a 👍 reaction on the reply.
- The chat closes with its button, with /start, or by itself after `IDLE_CLOSE` of silence.
- Logs carry ids and outcomes only, never message content.
"""

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
)
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.i18n import LOCALES, t
from czekachiko.keyboards import FEEDBACK_CANCEL, feedback_cancel, launcher
from czekachiko.render import replace_screen, show

log = logging.getLogger(__name__)

router = Router(name="feedback")
# `/start feedback` (the Mini App's «✉️ Написать нам» closes the app and lands here) and
# the reply-keyboard button. Both work from anywhere, even mid-flow.
entry = Router(name="feedback_entry")
admin_replies = Router(name="feedback_admin")
# The maintainer's messages that are not replies: a hint instead of the generic fallback.
admin_hint = Router(name="feedback_admin_hint")

MAX_LEN = 1000
PER_HOUR = 20
IDLE_CLOSE = timedelta(days=7)
CAPTION_MAX = 1024  # Telegram's limit for media captions
FEEDBACK_CLOSE = "fb:close"  # the close button under the maintainer's answers
BUTTON = {loc.MESSAGES["btn_feedback"] for loc in LOCALES.values()}
MEDIA = ("photo", "document", "video")
THUMBS_UP = [ReactionTypeEmoji(emoji="👍")]


class Feedback(StatesGroup):
    writing = State()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def media_of(msg: Message) -> str | None:
    return next((kind for kind in MEDIA if getattr(msg, kind)), None)


def supported(msg: Message) -> bool:
    return msg.text is not None or media_of(msg) is not None


def body_of(msg: Message) -> str:
    return (msg.text if msg.text is not None else msg.caption) or ""


def close_under_answer(lang: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=t(lang, "btn_close_support"), callback_data=FEEDBACK_CLOSE)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def _react(msg: Message) -> None:
    try:
        await msg.react(THUMBS_UP)
    except TelegramAPIError as e:  # reactions disabled, message gone, ...
        log.info("reaction failed: %s", e)


async def _relay(
    bot: Bot, msg: Message, to: int, header: str, kb: InlineKeyboardMarkup | None = None
) -> int:
    """Send `msg` to `to` under `header`: text as a new message, media as a copy."""
    body = body_of(msg)
    if media_of(msg) is None:
        sent = await bot.send_message(to, f"{header}\n\n{body}", reply_markup=kb, parse_mode=None)
        return sent.message_id
    caption = f"{header}\n\n{body}" if body else header
    copied = await bot.copy_message(
        chat_id=to,
        from_chat_id=msg.chat.id,
        message_id=msg.message_id,
        caption=caption[:CAPTION_MAX],
        parse_mode=None,
        reply_markup=kb,
    )
    return copied.message_id


# --- the user's side -------------------------------------------------------------------


@entry.message(CommandStart(deep_link=True, magic=F.args == "feedback"))
@entry.message(F.text.in_(BUTTON))
async def start_feedback(msg: Message, state: FSMContext, lang: str):
    await state.clear()
    await state.set_state(Feedback.writing)
    await state.update_data(since=_now())
    log.info("support chat opened user=%s", msg.from_user.id)
    await show(msg, t(lang, "feedback_prompt"), feedback_cancel(lang))


@router.callback_query(F.data == FEEDBACK_CANCEL)
async def close_from_prompt(cq: CallbackQuery, state: FSMContext, lang: str, webapp_url: str):
    await state.clear()
    log.info("support chat closed user=%s", cq.from_user.id)
    await show(cq, t(lang, "feedback_closed"), launcher(lang, webapp_url))


@router.callback_query(F.data == FEEDBACK_CLOSE)
async def close_from_answer(cq: CallbackQuery, state: FSMContext, lang: str, webapp_url: str):
    """Under an answer only the button goes away; the answer itself stays as it was."""
    await state.clear()
    log.info("support chat closed user=%s", cq.from_user.id)
    try:
        await cq.answer()
        if cq.message is not None:
            await cq.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError as e:
        log.info("closing tidy-up failed: %s", e)
    await replace_screen(
        cq.bot, cq.from_user.id, t(lang, "feedback_closed"), launcher(lang, webapp_url)
    )


@router.message(Feedback.writing)
async def user_message(
    msg: Message,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    admin_tg_id: int | None,
    webapp_url: str,
):
    uid = msg.from_user.id
    since = (await state.get_data()).get("since")
    if since is None or datetime.now(UTC) - datetime.fromisoformat(since) > IDLE_CLOSE:
        await state.clear()
        log.info("support chat expired user=%s", uid)
        await show(msg, t(lang, "unknown_message"), launcher(lang, webapp_url))
        return
    if not supported(msg):
        await msg.answer(t(lang, "feedback_text_only"))
        return
    body = body_of(msg)
    if len(body) > MAX_LEN:
        await msg.answer(f"⚠️ {t(lang, 'feedback_too_long')}")
        return
    hour_ago = datetime.now(UTC) - timedelta(hours=1)
    if await repo.count_feedback_since(session, uid, hour_ago) >= PER_HOUR:
        log.info("support rate limited user=%s", uid)
        await msg.answer(f"⏳ {t(lang, 'feedback_limit')}")
        return
    media = media_of(msg)
    row = await repo.add_feedback(session, uid, "in", body, media=media)
    await repo.log_feedback_send(session, uid)
    await state.update_data(since=_now())
    if admin_tg_id is not None:
        header = t("ru", "feedback_admin_header", id=row.id, tg=uid, ulang=lang)
        row.admin_msg_id = await _relay(msg.bot, msg, admin_tg_id, header)
    log.info("support in id=%s user=%s media=%s", row.id, uid, media)
    await _react(msg)


# --- the maintainer's side -------------------------------------------------------------


@admin_replies.message(F.reply_to_message)
async def admin_reply(
    msg: Message, session: AsyncSession, state: FSMContext, admin_tg_id: int | None
):
    if admin_tg_id is None or msg.from_user.id != admin_tg_id:
        raise SkipHandler
    replied = msg.reply_to_message.message_id
    original = await repo.feedback_by_admin_msg(session, replied)
    if original is None:
        log.info("support reply not matched to=%s", replied)
        await msg.reply(t("ru", "feedback_not_found"), parse_mode=None)
        return
    if not supported(msg):
        await msg.reply(t("ru", "feedback_text_only"), parse_mode=None)
        return
    uid = original.tg_id
    user = await repo.ensure_user(session, uid)
    header = t(user.lang, "feedback_reply_header")
    try:
        await _relay(msg.bot, msg, uid, header, close_under_answer(user.lang))
    except TelegramAPIError as e:  # blocked bot, deleted account, ...
        log.warning("support reply undelivered thread=%s user=%s: %s", original.id, uid, e)
        await msg.reply(t("ru", "feedback_undelivered"), parse_mode=None)
        return
    row = await repo.add_feedback(
        session, uid, "out", body_of(msg), media=media_of(msg), admin_msg_id=msg.message_id
    )
    # Reopen the user's chat, so their answer reaches the maintainer without a button.
    their_state = FSMContext(
        storage=state.storage, key=StorageKey(bot_id=msg.bot.id, chat_id=uid, user_id=uid)
    )
    await their_state.set_state(Feedback.writing)
    await their_state.update_data(since=_now())
    log.info("support out id=%s thread=%s user=%s delivered", row.id, original.id, uid)
    await _react(msg)


@admin_hint.message()
async def admin_without_reply(msg: Message, admin_tg_id: int | None):
    if admin_tg_id is None or msg.from_user.id != admin_tg_id:
        raise SkipHandler
    if (msg.text or "").startswith("/"):
        raise SkipHandler
    await msg.answer(t("ru", "feedback_admin_hint"), parse_mode=None)
