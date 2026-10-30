from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from czekachiko.i18n import t

# Opens the Main Mini App from any chat (enabled in BotFather).
APP_LINK = "https://t.me/czekachiko_bot?startapp"
FEEDBACK_CANCEL = "fb:cancel"


def reply_menu(lang: str) -> ReplyKeyboardMarkup:
    """Always-visible menu under the input field: the Mini App and feedback."""
    row = [
        # Plain text: Mini Apps opened from keyboard buttons receive no initData, so this
        # button is answered with the inline launcher instead (handlers/start.py).
        KeyboardButton(text=t(lang, "btn_open_app")),
        KeyboardButton(text=t(lang, "btn_feedback")),
    ]
    return ReplyKeyboardMarkup(keyboard=[row], resize_keyboard=True, is_persistent=True)


def launcher(lang: str, webapp_url: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        text=t(lang, "btn_open_webapp"), web_app=WebAppInfo(url=webapp_url)
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def feedback_cancel(lang: str) -> InlineKeyboardMarkup:
    """Closes the support chat (the callback data predates the chat: old prompts still work)."""
    button = InlineKeyboardButton(text=t(lang, "btn_close_support"), callback_data=FEEDBACK_CANCEL)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def open_bot(lang: str) -> InlineKeyboardMarkup:
    """Under inline cards in other chats, where web_app buttons are not allowed."""
    button = InlineKeyboardButton(text=t(lang, "btn_open_bot"), url=APP_LINK)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
