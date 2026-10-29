"""/start, the app launcher, and short answers to everything the bot no longer handles."""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from czekachiko.i18n import LOCALES, t
from czekachiko.keyboards import launcher, reply_menu
from czekachiko.render import refresh_reply_keyboard, show

log = logging.getLogger(__name__)
router = Router(name="start")
fallback = Router(name="fallback")
OPEN_APP = {loc.MESSAGES["btn_open_app"] for loc in LOCALES.values()}


@router.message(CommandStart())  # plain /start, `/start pick` from old links, any deep link
async def cmd_start(msg: Message, state: FSMContext, lang: str, webapp_url: str):
    await state.clear()
    # A message holds either an inline or a reply keyboard; the reply one goes in a carrier
    # message that is deleted at once, and the keyboard stays.
    await refresh_reply_keyboard(
        msg.bot, msg.from_user.id, t(lang, "keyboard_ready"), reply_menu(lang)
    )
    await show(msg, t(lang, "menu_title"), launcher(lang, webapp_url))


@router.message(F.text.in_(OPEN_APP))
async def open_app(msg: Message, state: FSMContext, lang: str, webapp_url: str):
    await state.clear()
    await show(msg, t(lang, "menu_title"), launcher(lang, webapp_url))


@fallback.callback_query()
async def stale_button(cq: CallbackQuery, state: FSMContext, lang: str):
    """Buttons of the old bot screens still sit in chats: a toast points to the app."""
    await state.clear()
    try:
        await cq.answer(t(lang, "stale_button"))
    except TelegramBadRequest as e:  # e.g. "query is too old" after a restart
        log.info("callback answer failed: %s", e)


@fallback.message()
async def unknown_message(msg: Message, state: FSMContext, lang: str, webapp_url: str):
    """Anything else, text or not: one line and the launcher. Nothing is stored."""
    await state.clear()  # also drops states of the removed flows still saved in the DB
    await show(msg, t(lang, "unknown_message"), launcher(lang, webapp_url))
