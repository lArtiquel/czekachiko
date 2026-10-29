import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from czekachiko.ui.screens import Screen

log = logging.getLogger(__name__)


async def show(event: Message | CallbackQuery, screen: Screen, new: bool = False) -> None:
    """Edit the live message for button presses; send a new one for typed input."""
    text, kb = screen
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except TelegramBadRequest as e:  # e.g. "query is too old" after a restart
            log.info("callback answer failed: %s", e)
        if not new and event.message is not None:
            try:
                await event.message.edit_text(text, reply_markup=kb)
                return
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    return
                log.info("edit failed, sending new message: %s", e)
        await event.bot.send_message(event.from_user.id, text, reply_markup=kb)
        return
    await event.answer(text, reply_markup=kb)
