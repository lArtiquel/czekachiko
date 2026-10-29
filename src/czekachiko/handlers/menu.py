"""The persistent reply keyboard: its buttons arrive as text and navigate from anywhere."""

from collections.abc import Callable
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.handlers.cases import start_add
from czekachiko.handlers.feedback import start_feedback
from czekachiko.i18n import LOCALES
from czekachiko.render import show
from czekachiko.ui import screens
from czekachiko.ui.keyboards import REPLY_MENU

router = Router(name="menu")
ROUTES = {loc.MESSAGES[key]: key for loc in LOCALES.values() for row in REPLY_MENU for key in row}


@router.message(F.text.in_(ROUTES))
async def reply_menu_button(
    msg: Message,
    session: AsyncSession,
    state: FSMContext,
    lang: str,
    calendar_url: str | None,
    clock: Callable[[], date],
):
    key = ROUTES[msg.text]
    if key == "btn_add":
        await start_add(msg, session, state, lang)
        return
    if key == "btn_feedback":
        await start_feedback(msg, state, lang)
        return
    await state.clear()
    if key == "btn_cases":
        screen = screens.cases_list(lang, await repo.list_cases(session, msg.from_user.id))
    elif key == "btn_stats":
        screen = screens.stats_pick_voiv(lang)
    elif key == "btn_calendar":
        screen = screens.calendar_view(lang, calendar_url)
    elif key == "btn_settings":
        user = await repo.ensure_user(session, msg.from_user.id)
        screen = screens.settings_view(lang, user.lang, user.reminders)
    elif key == "btn_share":
        screen = screens.share_view(lang)
    else:
        screen = screens.help_view(lang)
    await show(msg, screen)
