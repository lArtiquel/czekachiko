"""Test doubles for driving the dispatcher without Telegram."""

import itertools
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage | EditMessageText):
            chat_id = getattr(method, "chat_id", None) or 1
            return Message(
                message_id=next(_ids),
                date=NOW,
                chat=Chat(id=chat_id, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self):
        pass

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, SendMessage | EditMessageText)]

    def last(self):
        return [c for c in self.calls if isinstance(c, SendMessage | EditMessageText)][-1]

    def answered(self) -> int:
        return sum(isinstance(c, AnswerCallbackQuery) for c in self.calls)


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    return Bot(token="42:TEST", session=session), session


def _user(uid: int) -> User:
    return User(id=uid, is_bot=False, first_name="T", language_code="ru")


def text_update(uid: int, text: str) -> Update:
    msg = Message(
        message_id=next(_ids),
        date=NOW,
        chat=Chat(id=uid, type="private"),
        from_user=_user(uid),
        text=text,
    )
    return Update(update_id=next(_ids), message=msg)


def callback_update(uid: int, data: str) -> Update:
    msg = Message(message_id=next(_ids), date=NOW, chat=Chat(id=uid, type="private"), text="x")
    cq = CallbackQuery(
        id=str(next(_ids)), from_user=_user(uid), chat_instance="ci", message=msg, data=data
    )
    return Update(update_id=next(_ids), callback_query=cq)
