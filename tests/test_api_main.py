"""`python -m czekachiko.api`: migrations first, then serve on 0.0.0.0:8080."""

import re

from czekachiko.api import __main__ as entry
from czekachiko.config import Settings
from tests.test_compose import compose


def test_main_runs_migrations_then_serves(monkeypatch):
    calls = []
    monkeypatch.setenv("BOT_TOKEN", "42:TEST")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
    monkeypatch.setattr(entry, "run_migrations", lambda url: calls.append(("migrate", url)))

    def run_app(app, **kw):
        calls.append(("serve", kw["host"], kw["port"], kw["access_log_format"]))

    monkeypatch.setattr(entry.web, "run_app", run_app)
    entry.main()
    assert calls[0] == ("migrate", "postgresql+asyncpg://u:p@h/d")
    assert calls[1][:3] == ("serve", "0.0.0.0", 8080)
    assert "%{" not in calls[1][3]  # the access log never prints request headers


def test_bot_and_api_pools_fit_postgres_connection_limit():
    from czekachiko.db.session import MAX_OVERFLOW, POOL_SIZE

    command = " ".join(compose()["services"]["db"]["command"])
    max_connections = int(re.search(r"max_connections=(\d+)", command).group(1))
    backup = 1  # the nightly pg_dump
    bot = POOL_SIZE + MAX_OVERFLOW
    api = entry.POOL_SIZE + entry.MAX_OVERFLOW
    assert bot + api + backup <= max_connections


def test_webapp_url_setting():
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u:p@h/d", _env_file=None)
    assert s.webapp_url == "https://lartiquel.github.io/czekachiko/"
    s = Settings(
        bot_token="x",
        database_url="postgresql+asyncpg://u:p@h/d",
        webapp_url="https://example.org/app/",
        _env_file=None,
    )
    assert s.webapp_url == "https://example.org/app/"
