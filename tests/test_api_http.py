"""Transport-level behaviour of the API: auth, CORS, body limits, rate limits, errors."""

import logging
from urllib.parse import parse_qsl, urlencode

from aiohttp import web

from czekachiko.api.limits import RateLimiter
from tests.fakes import TOKEN, sign_init_data

ORIGIN = "https://lartiquel.github.io"


# --- limiter ---------------------------------------------------------------------------


def test_bucket_allows_burst_then_refills():
    t = [0.0]
    limiter = RateLimiter(burst=3, per_second=1, now=lambda: t[0])
    assert [limiter.take("a") for _ in range(4)] == [0, 0, 0, 1]
    assert limiter.take("b") == 0  # keys are independent
    t[0] = 1.0
    assert limiter.take("a") == 0
    assert limiter.take("a") == 1


def test_bucket_retry_after_rounds_up():
    t = [0.0]
    limiter = RateLimiter(burst=1, per_second=0.25, now=lambda: t[0])
    assert limiter.take("a") == 0
    assert limiter.take("a") == 4


def test_bucket_memory_is_bounded():
    t = [0.0]
    limiter = RateLimiter(burst=2, per_second=1, now=lambda: t[0], max_keys=10)
    limiter.take("limited")
    limiter.take("limited")
    for i in range(50):
        limiter.take(f"k{i}")
    assert len(limiter.buckets) <= 10
    assert limiter.take("limited") == 1  # a client at its limit is kept, not forgotten


# --- health and auth -------------------------------------------------------------------


async def test_health_needs_no_auth(api):
    r = await api.call("GET", "/api/health", signed=False)
    assert r.status == 200 and await r.json() == {"ok": True}


async def test_no_header_is_401(api):
    r = await api.call("GET", "/api/me", signed=False)
    assert r.status == 401 and await r.json() == {"error": "unauthorized"}


async def test_every_bad_credential_is_401(api):
    good = sign_init_data(auth_date=int(api.time.t))
    tampered = dict(parse_qsl(good))
    tampered["user"] = tampered["user"].replace("548", "549")
    headers = [
        f"Bearer {good}",
        "tma",
        "tma ",
        f"tma {urlencode(tampered)}",
        f"tma {sign_init_data(token='43:OTHER', auth_date=int(api.time.t))}",
        f"tma {sign_init_data(auth_date=int(api.time.t) - 25 * 3600)}",
        f"tma {sign_init_data(auth_date=int(api.time.t) + 3600)}",
        f"tma {sign_init_data(user='{oops', auth_date=int(api.time.t))}",
    ]
    for h in headers:
        r = await api.call("GET", "/api/me", signed=False, headers={"Authorization": h})
        assert r.status == 401, h
        assert await r.json() == {"error": "unauthorized"}


async def test_valid_init_data_reaches_the_handler(api):
    assert (await api.json("GET", "/api/me", uid=777))["tg_id"] == 777


async def test_unknown_api_route_without_auth_is_401_and_with_auth_404(api):
    assert (await api.call("GET", "/api/nope", signed=False)).status == 401
    assert await api.json("GET", "/api/nope", status=404) == {"error": "not_found"}


async def test_wrong_method_is_405_json(api):
    assert await api.json("POST", "/api/health", status=405, signed=False) == {
        "error": "method_not_allowed"
    }


# --- CORS ------------------------------------------------------------------------------


async def test_preflight_from_allowed_origin(api):
    r = await api.call(
        "OPTIONS",
        "/api/cases",
        signed=False,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert r.status == 204
    assert r.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert set(r.headers["Access-Control-Allow-Methods"].split(", ")) == {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }
    assert r.headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type"
    assert r.headers["Access-Control-Max-Age"] == "600"
    assert "Origin" in r.headers["Vary"]


async def test_preflight_from_other_origin_is_refused(api):
    r = await api.call(
        "OPTIONS",
        "/api/cases",
        signed=False,
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status == 403
    assert "Access-Control-Allow-Origin" not in r.headers


async def test_request_from_other_origin_is_refused(api):
    r = await api.call("GET", "/api/me", headers={"Origin": "https://lartiquel.github.io.evil"})
    assert r.status == 403 and await r.json() == {"error": "forbidden"}
    assert "Access-Control-Allow-Origin" not in r.headers


async def test_allowed_origin_gets_cors_headers_even_on_errors(api):
    ok = await api.call("GET", "/api/me", headers={"Origin": ORIGIN})
    assert ok.status == 200 and ok.headers["Access-Control-Allow-Origin"] == ORIGIN
    denied = await api.call("GET", "/api/me", signed=False, headers={"Origin": ORIGIN})
    assert denied.status == 401 and denied.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "Retry-After" in denied.headers["Access-Control-Expose-Headers"]


# --- bodies ----------------------------------------------------------------------------


async def test_body_over_16kb_is_413(api):
    r = await api.call(
        "POST",
        "/api/cases",
        data=b'{"x":"' + b"a" * 17_000 + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status == 413 and await r.json() == {"error": "too_large"}


async def test_chunked_body_over_16kb_is_413(api):
    async def chunks():
        for _ in range(20):
            yield b"a" * 1024

    r = await api.call(
        "POST", "/api/cases", data=chunks(), headers={"Content-Type": "application/json"}
    )
    assert r.status == 413


async def test_writes_must_be_json(api):
    r = await api.call("POST", "/api/cases", data="voivodeship=x")
    assert r.status == 415 and await r.json() == {"error": "unsupported_media_type"}


async def test_malformed_json_is_400(api):
    for raw in (b"{", b"[1, 2]", b'"text"', b"[" * 5000 + b"]" * 5000):
        r = await api.call(
            "POST", "/api/cases", data=raw, headers={"Content-Type": "application/json"}
        )
        assert r.status == 400, raw[:10]
        assert await r.json() == {"error": "bad_json"}


# --- rate limits -----------------------------------------------------------------------


async def test_per_user_burst_gives_429_with_retry_after(api):
    api.time.step = 0
    statuses = [(await api.call("GET", "/api/me")).status for _ in range(10)]
    assert statuses == [200] * 10
    r = await api.call("GET", "/api/me")
    assert r.status == 429 and await r.json() == {"error": "rate_limited"}
    assert int(r.headers["Retry-After"]) >= 1
    assert (await api.call("GET", "/api/me", uid=999)).status == 200  # other users unaffected
    api.time.t += int(r.headers["Retry-After"])
    assert (await api.call("GET", "/api/me")).status == 200


async def test_per_user_sustained_rate_is_two_per_second(api):
    api.time.step = 0
    for _ in range(10):
        await api.call("GET", "/api/me")
    api.time.t += 5  # refills 10 tokens at 2/s, never more than the burst
    statuses = [(await api.call("GET", "/api/me")).status for _ in range(11)]
    assert statuses.count(429) == 1


async def test_per_ip_limit_applies_before_auth(api):
    api.time.step = 0
    ip = {"CF-Connecting-IP": "203.0.113.7"}
    for _ in range(300):
        assert (await api.call("GET", "/api/me", signed=False, headers=ip)).status == 401
    r = await api.call("GET", "/api/me", signed=False, headers=ip)
    assert r.status == 429 and "Retry-After" in r.headers
    other = {"CF-Connecting-IP": "203.0.113.8"}
    assert (await api.call("GET", "/api/me", signed=False, headers=other)).status == 401


# --- errors and logs -------------------------------------------------------------------


async def test_unhandled_error_is_generic_500_without_traceback(make_api, caplog):
    async def boom(request):
        raise RuntimeError("secret internals")

    def extend(app):
        app.router.add_get("/api/boom", boom)

    async with make_api(extend) as api:
        with caplog.at_level(logging.DEBUG):
            r = await api.call("GET", "/api/boom")
            body = await r.text()
    assert r.status == 500
    assert body == '{"error": "internal"}'
    assert "Traceback" not in body and "secret" not in body


async def test_logs_never_contain_init_data_or_token(api, caplog):
    with caplog.at_level(logging.DEBUG):
        good = api.auth()["Authorization"]
        await api.call("GET", "/api/me", signed=False, headers={"Authorization": good + "x"})
        await api.call("GET", "/api/me", signed=False, headers={"Authorization": good})
    hash_ = dict(parse_qsl(good[4:]))["hash"]
    assert hash_ not in caplog.text and TOKEN not in caplog.text


async def test_db_session_commits_on_success_only(make_api, session_factory):
    from czekachiko.api.app import SESSION, TG_ID
    from czekachiko.db import repo

    async def write_then_fail(request):
        await repo.set_lang(request[SESSION], request[TG_ID], "en")
        return web.json_response({"error": "nope"}, status=422)

    def extend(app):
        app.router.add_post("/api/fail", write_then_fail)

    async with make_api(extend) as api:
        await api.call("POST", "/api/fail")
        assert (await api.json("GET", "/api/me"))["lang"] == "ru"
        await api.json("PATCH", "/api/me", json={"lang": "en"})
    async with session_factory() as s:
        assert (await repo.ensure_user(s, 548)).lang == "en"
