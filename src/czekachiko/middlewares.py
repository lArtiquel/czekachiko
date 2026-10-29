import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

from czekachiko.db import repo

log = logging.getLogger(__name__)
Handler = Callable[[Any, dict[str, Any]], Awaitable[Any]]


class ThrottleMiddleware(BaseMiddleware):
    """Per-user flood control. Over-limit updates are dropped silently."""

    def __init__(
        self,
        rate: int = 5,
        per: float = 3.0,
        ban_after_per_min: int = 40,
        ban_seconds: int = 600,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.rate, self.per = rate, per
        self.ban_after, self.ban_seconds = ban_after_per_min, ban_seconds
        self.clock = clock
        self.hits: dict[int, deque[float]] = defaultdict(deque)
        self.banned_until: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: Any, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        now = self.clock()
        if self.banned_until.get(user.id, 0) > now:
            return None
        hits = self.hits[user.id]
        hits.append(now)
        while hits and hits[0] < now - 60:
            hits.popleft()
        if len(hits) > self.ban_after:
            self.banned_until[user.id] = now + self.ban_seconds
            hits.clear()
            log.warning("flood: user muted for %ss", self.ban_seconds)
            return None
        recent = sum(1 for h in hits if h > now - self.per)
        if recent > self.rate:
            return None
        return await handler(event, data)


class DbMiddleware(BaseMiddleware):
    """One session per update; commits on success. Also loads the user's language."""

    def __init__(self, factory: async_sessionmaker):
        self.factory = factory

    async def __call__(self, handler: Handler, event: Any, data: dict[str, Any]) -> Any:
        async with self.factory() as session:
            data["session"] = session
            user = data.get("event_from_user")
            if user is not None:
                data["lang"] = (await repo.ensure_user(session, user.id)).lang
            result = await handler(event, data)
            await session.commit()
            return result


class ConcurrencyMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 20):
        self.sem = asyncio.Semaphore(limit)

    async def __call__(self, handler: Handler, event: Any, data: dict[str, Any]) -> Any:
        async with self.sem:
            return await handler(event, data)
