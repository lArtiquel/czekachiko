"""Fixes from the pre-launch security review."""

import asyncio
import json
import logging

import pytest

ORIGIN = "https://lartiquel.github.io"


class SpyFactory:
    """Wraps a session factory and counts open sessions."""

    def __init__(self, inner):
        self.inner, self.open = inner, 0

    def __call__(self):
        spy = self
        cm = self.inner()

        class Wrapped:
            async def __aenter__(self):
                spy.open += 1
                return await cm.__aenter__()

            async def __aexit__(self, *exc):
                spy.open -= 1
                return await cm.__aexit__(*exc)

        return Wrapped()


async def test_slow_body_holds_no_db_connection(session_factory, db_url, api_time, monkeypatch):
    from datetime import date

    from aiohttp.test_utils import TestClient, TestServer

    from czekachiko.api import app as app_mod
    from czekachiko.config import Settings
    from tests.fakes import TOKEN, Api

    monkeypatch.setattr(app_mod, "BODY_TIMEOUT", 0.5)
    spy = SpyFactory(session_factory)
    settings = Settings(bot_token=TOKEN, database_url=db_url, _env_file=None)
    app = app_mod.create_app(settings, spy, clock=lambda: date(2026, 10, 29), now=api_time)
    async with TestClient(TestServer(app)) as client:
        api = Api(client, api_time)

        async def trickle():
            yield b'{"voivodeship":'
            await asyncio.sleep(2)  # never finishes within BODY_TIMEOUT
            yield b'"mazowieckie"}'

        task = asyncio.create_task(
            api.call(
                "POST", "/api/cases", data=trickle(), headers={"Content-Type": "application/json"}
            )
        )
        await asyncio.sleep(0.3)
        assert spy.open == 0  # nothing checked out while the body is still arriving
        r = await task
        assert r.status == 408


async def test_lone_surrogate_doc_name_is_422_and_not_logged(api, caplog):
    case = await api.json(
        "POST",
        "/api/cases",
        201,
        json={
            "voivodeship": "mazowieckie",
            "purpose": "jdg",
            "channel": "mos",
            "filed": "2026-03-06",
            "client_token": "abcdefgh12",
        },
    )
    raw = '{"name": "SECRET-DOC \\ud800", "date": null}'
    with caplog.at_level(logging.DEBUG):
        r = await api.call(
            "POST",
            f"/api/cases/{case['id']}/documents",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
    assert r.status == 422
    assert "SECRET-DOC" not in caplog.text


@pytest.mark.parametrize("lang", [[], {}, 1, None])
async def test_patch_me_rejects_non_string_lang(api, lang):
    await api.json("PATCH", "/api/me", 422, json={"lang": lang})


async def test_security_headers(api):
    r = await api.call("GET", "/api/me")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Cache-Control"] == "no-store"
    assert "aiohttp" not in r.headers.get("Server", "")


async def test_allowed_origin_follows_webapp_url(session_factory, db_url, api_time):
    from datetime import date

    from aiohttp.test_utils import TestClient, TestServer

    from czekachiko.api.app import create_app
    from czekachiko.config import Settings
    from tests.fakes import TOKEN, Api

    settings = Settings(
        bot_token=TOKEN, database_url=db_url, webapp_url="https://example.org/a/", _env_file=None
    )
    app = create_app(settings, session_factory, clock=lambda: date(2026, 10, 29), now=api_time)
    async with TestClient(TestServer(app)) as client:
        api = Api(client, api_time)
        ok = await api.call("GET", "/api/me", headers={"Origin": "https://example.org"})
        bad = await api.call("GET", "/api/me", headers={"Origin": ORIGIN})
    assert ok.status == 200 and bad.status == 403


def test_clean_name_rejects_surrogates_and_unassigned():
    from czekachiko.documents import clean_name

    assert clean_name("Umowa \ud800")[0] is None
    assert clean_name("Umowa \U000e0000")[0] is None  # unassigned code point
    assert clean_name("Umowa B2B")[0] == "Umowa B2B"


def test_engine_hides_parameters_and_api_has_timeouts():
    from czekachiko.db.session import make_session_factory

    engine, _ = make_session_factory("postgresql+asyncpg://u:p@h/d", api=True)
    assert engine.sync_engine.hide_parameters is True
    assert engine.pool.timeout() <= 5
    json.dumps(1)
