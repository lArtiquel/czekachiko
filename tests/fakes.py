"""Test doubles for driving the dispatcher without Telegram."""

import itertools
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Message, MessageId, PhotoSize, Update, User

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.fail_answer = False
        self.sent_ids: dict[int, int] = {}  # call index -> message_id of sent messages
        self.blocked: set[int] = set()  # chats that blocked the bot

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if self.fail_answer and isinstance(method, AnswerCallbackQuery):
            from aiogram.exceptions import TelegramBadRequest

            raise TelegramBadRequest(method=method, message="query is too old")
        if getattr(method, "chat_id", None) in self.blocked:
            from aiogram.exceptions import TelegramForbiddenError

            raise TelegramForbiddenError(method=method, message="bot was blocked by the user")
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(_ids))
        if isinstance(method, SendMessage | EditMessageText):
            chat_id = getattr(method, "chat_id", None) or 1
            mid = next(_ids) if isinstance(method, SendMessage) else (method.message_id or 0)
            if isinstance(method, SendMessage):
                self.sent_ids[len(self.calls) - 1] = mid
            return Message(
                message_id=mid,
                date=NOW,
                chat=Chat(id=chat_id, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self):
        pass

    def last_sent_id(self) -> int:
        return self.sent_ids[max(self.sent_ids)]

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


def photo_update(uid: int, caption: str | None = None, reply_to: Message | None = None) -> Update:
    msg = Message(
        message_id=next(_ids),
        date=NOW,
        chat=Chat(id=uid, type="private"),
        from_user=_user(uid),
        photo=[PhotoSize(file_id="f", file_unique_id="u", width=10, height=10)],
        caption=caption,
        reply_to_message=reply_to,
    )
    return Update(update_id=next(_ids), message=msg)


def callback_update(uid: int, data: str) -> Update:
    msg = Message(message_id=next(_ids), date=NOW, chat=Chat(id=uid, type="private"), text="x")
    cq = CallbackQuery(
        id=str(next(_ids)), from_user=_user(uid), chat_instance="ci", message=msg, data=data
    )
    return Update(update_id=next(_ids), callback_query=cq)


# --- Mini App initData -----------------------------------------------------------------

TOKEN = "42:TEST"


def sign_init_data(
    token: str = TOKEN,
    *,
    user: dict | str | None = None,
    auth_date: int | None = None,
    extra: dict | None = None,
) -> str:
    """initData as Telegram builds it: the fields plus hash = HMAC over the sorted fields."""
    import hashlib
    import hmac
    import json
    from urllib.parse import urlencode

    if user is None:
        user = {"id": 548, "first_name": "T", "language_code": "ru"}
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(NOW.timestamp())),
        "query_id": "AAH-test",
        "user": user if isinstance(user, str) else json.dumps(user, separators=(",", ":")),
        **(extra or {}),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class FakeTime:
    """Injectable epoch clock. Each signed request moves it forward by `step` seconds, so
    ordinary tests never trip the rate limits; set step to 0 to freeze time."""

    def __init__(self, t: float, step: float = 0.5):
        self.t, self.step = t, step

    def __call__(self) -> float:
        return self.t


class Api:
    """aiohttp TestClient plus a valid `Authorization: tma …` header per request."""

    def __init__(self, client, time: FakeTime, uid: int = 548):
        self.client, self.time, self.uid = client, time, uid

    def auth(self, uid: int | None = None) -> dict[str, str]:
        user = {"id": uid or self.uid, "first_name": "T"}
        return {"Authorization": "tma " + sign_init_data(user=user, auth_date=int(self.time.t))}

    async def call(self, method: str, path: str, *, uid: int | None = None, signed=True, **kw):
        self.time.t += self.time.step
        headers = {**(self.auth(uid) if signed else {}), **kw.pop("headers", {})}
        return await self.client.request(method, path, headers=headers, **kw)

    async def json(self, method: str, path: str, status: int = 200, **kw):
        r = await self.call(method, path, **kw)
        body = await r.json() if r.status != 204 else None
        assert r.status == status, (r.status, body)
        return body
