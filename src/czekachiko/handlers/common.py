"""Commands, top-level navigation and the catch-all fallbacks."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.i18n import t
from czekachiko.render import show
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Act, Nav, Noop, reply_menu

router = Router(name="common")
fallback = Router(name="fallback")


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, lang: str):
    await state.clear()
    await msg.answer(screens.start_text(lang), reply_markup=reply_menu(lang))


@router.message(Command("help"))
async def cmd_help(msg: Message, lang: str):
    await show(msg, screens.help_view(lang))


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext, lang: str):
    await state.clear()
    await show(msg, screens.main_menu(lang))


@router.message(Command("cases"))
async def cmd_cases(msg: Message, session: AsyncSession, state: FSMContext, lang: str):
    await state.clear()
    await show(msg, screens.cases_list(lang, await repo.list_cases(session, msg.from_user.id)))


@router.message(Command("add"))
async def cmd_add(msg: Message, lang: str):
    await show(msg, (t(lang, "btn_add"), screens.markup_one(lang, "btn_add", Nav(to="add"))))


@router.message(Command("stats"))
async def cmd_stats(msg: Message, state: FSMContext, lang: str):
    await state.clear()
    await show(msg, screens.stats_pick_voiv(lang))


@router.message(Command("settings"))
async def cmd_settings(msg: Message, session: AsyncSession, state: FSMContext, lang: str):
    await state.clear()
    user = await repo.ensure_user(session, msg.from_user.id)
    await show(msg, screens.settings_view(lang, user.lang, user.reminders))


@router.callback_query(Nav.filter(F.to == "menu"))
async def nav_menu(cq: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await show(cq, screens.main_menu(lang))


@router.callback_query(Act.filter(F.action == "cancel"))
async def act_cancel(cq: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await show(cq, screens.main_menu(lang))


@router.callback_query(Nav.filter(F.to == "help"))
async def nav_help(cq: CallbackQuery, lang: str):
    await show(cq, screens.help_view(lang))


@router.callback_query(Nav.filter(F.to == "privacy"))
async def nav_privacy(cq: CallbackQuery, lang: str):
    await show(cq, screens.privacy(lang))


@router.callback_query(Noop.filter())
async def noop(cq: CallbackQuery):
    await cq.answer()


@fallback.callback_query()
async def stale_callback(cq: CallbackQuery, state: FSMContext, lang: str):
    """Old, foreign or unparseable buttons land here: show the menu, never error."""
    await state.clear()
    await show(cq, screens.main_menu(lang))


@fallback.message()
async def stray_message(msg: Message, lang: str):
    """No free text anywhere: point back to the buttons."""
    await msg.answer(t(lang, "err_use_buttons"))
    await show(msg, screens.main_menu(lang))
