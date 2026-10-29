"""Show screens while keeping the chat tidy: one live bot screen, no leftover inputs."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup

from czekachiko.ui.screens import Screen

log = logging.getLogger(__name__)

# user id -> message id of the bot's current screen. In memory on purpose: after a restart
# the worst case is one old screen left in the chat.
LIVE: dict[int, int] = {}


async def _delete(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramAPIError as e:  # too old, already gone, ...
        log.debug("delete failed: %s", e)


async def replace_screen(bot: Bot, user_id: int, text: str, kb) -> Message:
    """Send a fresh screen at the bottom of the chat and remove the previous one."""
    old = LIVE.get(user_id)
    msg = await bot.send_message(user_id, text, reply_markup=kb)
    LIVE[user_id] = msg.message_id
    if old and old != msg.message_id:
        await _delete(bot, user_id, old)
    return msg


async def show(
    event: Message | CallbackQuery, screen: Screen, new: bool = False, answer: bool = True
) -> None:
    """Edit the live message for button presses; for typed input replace it and tidy up."""
    text, kb = screen
    if isinstance(event, CallbackQuery):
        if answer:
            try:
                await event.answer()
            except TelegramBadRequest as e:  # e.g. "query is too old" after a restart
                log.info("callback answer failed: %s", e)
        if not new and event.message is not None:
            try:
                await event.message.edit_text(text, reply_markup=kb)
                LIVE[event.from_user.id] = event.message.message_id
                return
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    return
                log.info("edit failed, sending new message: %s", e)
        await replace_screen(event.bot, event.from_user.id, text, kb)
        return
    await _delete(event.bot, event.chat.id, event.message_id)  # the user's own input
    await replace_screen(event.bot, event.from_user.id, text, kb)


async def refresh_reply_keyboard(
    bot: Bot, user_id: int, text: str, kb: ReplyKeyboardMarkup
) -> None:
    """A reply keyboard can only change with a message; send one and delete it at once.
    The keyboard stays."""
    msg = await bot.send_message(user_id, text, reply_markup=kb)
    await _delete(bot, user_id, msg.message_id)
