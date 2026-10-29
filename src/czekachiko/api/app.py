"""The aiohttp application: middlewares (CORS, errors, limits, auth, DB session) and routes.

Never log request headers: the Authorization header carries the user's signed initData.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import date

from aiohttp import web
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from czekachiko.api.auth import user_id_from_init_data
from czekachiko.api.limits import RateLimiter
from czekachiko.config import Settings
from czekachiko.db import repo
from czekachiko.db.models import User

log = logging.getLogger(__name__)

ALLOWED_ORIGIN = "https://lartiquel.github.io"
CORS_PREFLIGHT = {
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "600",
}
MAX_BODY = 16 * 1024
PUBLIC_PATHS = {"/api/health"}
USER_BURST, USER_PER_SECOND = 10, 120 / 60
IP_BURST, IP_PER_SECOND = 300, 300 / 60
# Namespace for per-user write locks; the two-key advisory lock space never overlaps the
# single-key locks repo.recompute_for takes.
USER_LOCK_NS = 0x637A

CLOCK = web.AppKey("clock", Callable)
TG_ID = web.RequestKey("tg_id", int)
SESSION = web.RequestKey("session", AsyncSession)
USER = web.RequestKey("user", User)
STATUS_ERRORS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


class ApiError(Exception):
    """An expected failure, answered as a JSON body: {"error": code, **extra}."""

    def __init__(self, status: int, error: str, headers: dict | None = None, **extra):
        super().__init__(error)
        self.status, self.headers = status, headers or {}
        self.body = {"error": error, **extra}


async def read_json(request: web.Request) -> dict:
    """The request body as a JSON object; 415 for other content types, 400 if malformed."""
    if request.content_type != "application/json":
        raise ApiError(415, "unsupported_media_type")
    try:
        body = json.loads(await request.read())
    except (ValueError, RecursionError):
        raise ApiError(400, "bad_json") from None
    if not isinstance(body, dict):
        raise ApiError(400, "bad_json")
    return body


@web.middleware
async def cors(request: web.Request, handler):
    origin = request.headers.get("Origin")
    if origin is not None and origin != ALLOWED_ORIGIN:
        return web.json_response({"error": "forbidden"}, status=403)
    if request.method == "OPTIONS":
        response = web.Response(status=204, headers=CORS_PREFLIGHT)
    else:
        response = await handler(request)
    response.headers["Vary"] = "Origin"
    if origin is not None:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Expose-Headers"] = "Retry-After"
    return response


@web.middleware
async def errors(request: web.Request, handler):
    """Every failure becomes a short JSON body; tracebacks go to the log only."""
    try:
        return await handler(request)
    except ApiError as e:
        return web.json_response(e.body, status=e.status, headers=e.headers)
    except web.HTTPException as e:
        if e.status < 400:
            raise
        return web.json_response({"error": STATUS_ERRORS.get(e.status, "error")}, status=e.status)
    except Exception:
        # The path holds only numeric ids and enum codes; never log headers or bodies.
        log.exception("unhandled error: %s %s", request.method, request.path)
        return web.json_response({"error": "internal"}, status=500)


@web.middleware
async def body_limit(request: web.Request, handler):
    # Bodies without a length are cut off by client_max_size when read.
    if (request.content_length or 0) > MAX_BODY:
        raise ApiError(413, "too_large")
    return await handler(request)


def client_ip(request: web.Request) -> str:
    # Only the tunnel can reach the API, and Cloudflare sets this header itself.
    return (request.headers.get("CF-Connecting-IP") or request.remote or "?")[:64]


def rate_limit(limiter: RateLimiter, key: Callable[[web.Request], object]):
    @web.middleware
    async def middleware(request: web.Request, handler):
        k = key(request)
        if k is not None and (wait := limiter.take(k)):
            raise ApiError(429, "rate_limited", headers={"Retry-After": str(wait)})
        return await handler(request)

    return middleware


def authenticate(bot_token: str, now: Callable[[], float]):
    @web.middleware
    async def middleware(request: web.Request, handler):
        if not request.path.startswith("/api/") or request.path in PUBLIC_PATHS:
            return await handler(request)
        scheme, _, init_data = request.headers.get("Authorization", "").partition(" ")
        uid = user_id_from_init_data(init_data, bot_token, now()) if scheme == "tma" else None
        if uid is None:
            raise ApiError(401, "unauthorized")
        request[TG_ID] = uid
        return await handler(request)

    return middleware


def db_session(factory: async_sessionmaker):
    """One session per authenticated request, committed when the response is a success.

    Writes take a per-user lock for the transaction, so double submits of the same form
    run one after the other (idempotency token, case and document limits).
    """

    @web.middleware
    async def middleware(request: web.Request, handler):
        tg_id = request.get(TG_ID)
        if tg_id is None:
            return await handler(request)
        async with factory() as s:
            if request.method not in ("GET", "HEAD"):
                await s.execute(
                    text("SELECT pg_advisory_xact_lock(:ns, hashtext(:k))"),
                    {"ns": USER_LOCK_NS, "k": str(tg_id)},
                )
            request[SESSION] = s
            request[USER] = await repo.ensure_user(s, tg_id)
            response = await handler(request)
            if response.status < 400:
                await s.commit()
            return response

    return middleware


def create_app(
    settings: Settings,
    session_factory: async_sessionmaker,
    *,
    clock: Callable[[], date] = date.today,
    now: Callable[[], float] = time.time,
) -> web.Application:
    from czekachiko.api.views import routes

    per_ip = RateLimiter(IP_BURST, IP_PER_SECOND, now)
    per_user = RateLimiter(USER_BURST, USER_PER_SECOND, now)
    app = web.Application(
        client_max_size=MAX_BODY,
        middlewares=[
            cors,
            errors,
            rate_limit(per_ip, client_ip),
            body_limit,
            authenticate(settings.bot_token.get_secret_value(), now),
            rate_limit(per_user, lambda r: r.get(TG_ID)),
            db_session(session_factory),
        ],
    )
    app[CLOCK] = clock
    app.add_routes(routes)
    return app
