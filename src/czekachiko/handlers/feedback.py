"""User → maintainer feedback, and the maintainer's replies back to that one user."""

from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.i18n import t
from czekachiko.render import flash, show
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Nav

router = Router(name="feedback")
admin_replies = Router(name="feedback_admin")

MAX_LEN = 1000
PER_HOUR = 5


class Feedback(StatesGroup):
    writing = State()


async def start_feedback(event, state: FSMContext, lang: str) -> None:
    await state.clear()
    await state.set_state(Feedback.writing)
    await show(event, screens.feedback_prompt(lang))


@router.callback_query(Nav.filter(F.to == "feedback"))
async def feedback_button(cq: CallbackQuery, state: FSMContext, lang: str):
    await start_feedback(cq, state, lang)


@router.message(Feedback.writing, F.text)
async def feedback_text(
    msg: Message,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    admin_tg_id: int | None,
    ephemeral_delay: float,
):
    text = msg.text.strip()
    if len(text) > MAX_LEN:
        prompt, kb = screens.feedback_prompt(lang)
        await show(msg, (f"⚠️ {t(lang, 'feedback_too_long')}\n\n{prompt}", kb))
        return
    since = datetime.now(UTC) - timedelta(hours=1)
    if await repo.count_feedback_since(session, msg.from_user.id, since) >= PER_HOUR:
        await state.clear()
        menu_text, kb = screens.main_menu(lang)
        await show(msg, (f"⏳ {t(lang, 'feedback_limit')}\n\n{menu_text}", kb))
        return
    row = await repo.add_feedback(session, msg.from_user.id, "in", text)
    if admin_tg_id is not None:
        header = t("ru", "feedback_admin_header", id=row.id, tg=msg.from_user.id, ulang=lang)
        sent = await msg.bot.send_message(admin_tg_id, f"{header}\n\n{text}", parse_mode=None)
        row.admin_msg_id = sent.message_id
    await state.clear()
    await show(msg, screens.main_menu(lang))
    await flash(msg.bot, msg.from_user.id, t(lang, "feedback_sent"), ephemeral_delay)


@router.message(Feedback.writing)
async def feedback_not_text(msg: Message, lang: str):
    prompt, kb = screens.feedback_prompt(lang)
    await show(msg, (f"⚠️ {t(lang, 'feedback_text_only')}\n\n{prompt}", kb))


@admin_replies.message(F.reply_to_message, F.text)
async def admin_reply(msg: Message, session: AsyncSession, admin_tg_id: int | None):
    if admin_tg_id is None or msg.from_user.id != admin_tg_id:
        raise SkipHandler
    original = await repo.feedback_by_admin_msg(session, msg.reply_to_message.message_id)
    if original is None:
        await msg.answer(t("ru", "feedback_not_found"), parse_mode=None)
        return
    user = await repo.ensure_user(session, original.tg_id)
    body = f"{t(user.lang, 'feedback_reply_header')}\n\n{msg.text}"
    try:
        await msg.bot.send_message(original.tg_id, body, parse_mode=None)
    except Exception:  # noqa: BLE001 — blocked bot, deleted account, ...
        await msg.answer(t("ru", "feedback_undelivered"), parse_mode=None)
        return
    await repo.add_feedback(session, original.tg_id, "out", msg.text)
    await msg.answer(t("ru", "feedback_delivered"), parse_mode=None)
