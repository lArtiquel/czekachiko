from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko.db import repo
from czekachiko.i18n import t
from czekachiko.render import refresh_reply_keyboard, show
from czekachiko.ui import screens
from czekachiko.ui.keyboards import Act, Nav, reply_menu

router = Router(name="settings")


async def _settings(event, session: AsyncSession, user_id: int):
    user = await repo.ensure_user(session, user_id)
    await show(event, screens.settings_view(user.lang, user.lang, user.reminders))


@router.callback_query(Nav.filter(F.to == "settings"))
async def settings(cq: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    await _settings(cq, session, cq.from_user.id)


@router.callback_query(Act.filter(F.action == "lang"))
async def switch_lang(cq: CallbackQuery, callback_data: Act, session: AsyncSession):
    if callback_data.value in ("ru", "en"):
        new_lang = callback_data.value
        await repo.set_lang(session, cq.from_user.id, new_lang)
        await cq.answer(t(new_lang, "lang_changed"))  # disappearing toast
        await refresh_reply_keyboard(
            cq.bot, cq.from_user.id, t(new_lang, "lang_changed"), reply_menu(new_lang)
        )
        user = await repo.ensure_user(session, cq.from_user.id)
        await show(cq, screens.settings_view(user.lang, user.lang, user.reminders), answer=False)
        return
    await _settings(cq, session, cq.from_user.id)


@router.callback_query(Act.filter(F.action == "reminders"))
async def toggle_reminders(cq: CallbackQuery, session: AsyncSession):
    user = await repo.ensure_user(session, cq.from_user.id)
    await repo.set_reminders(session, cq.from_user.id, not user.reminders)
    await _settings(cq, session, cq.from_user.id)


@router.callback_query(Act.filter(F.action == "del_all"))
async def del_all(cq: CallbackQuery, lang: str):
    await show(cq, screens.confirm_delete_all(lang))


@router.callback_query(Act.filter(F.action == "del_all_yes"))
async def del_all_yes(cq: CallbackQuery, session: AsyncSession, state: FSMContext, lang: str):
    await repo.delete_user(session, cq.from_user.id)
    await state.clear()
    await cq.answer()
    await cq.message.edit_text(t(lang, "all_deleted"))


@router.callback_query(Nav.filter(F.to == "calendar"))
async def calendar(cq: CallbackQuery, session: AsyncSession, lang: str):
    await show(cq, screens.calendar_view(lang, await repo.calendar_links(session)))


@router.message(Command("calendar"))
async def cmd_calendar(msg: Message, session: AsyncSession, lang: str):
    await show(msg, screens.calendar_view(lang, await repo.calendar_links(session)))
