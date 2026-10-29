from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_compose_has_no_published_ports_and_internal_db():
    c = compose()
    for name, svc in c["services"].items():
        assert "ports" not in svc, name
        assert "network_mode" not in svc, name
        for key in ("mem_limit", "cpus", "pids_limit", "logging"):
            assert key in svc, f"{name} missing {key}"
    assert c["networks"]["db"]["internal"] is True
    assert c["services"]["db"]["networks"] == ["db"]
    assert sorted(c["services"]["bot"]["networks"]) == ["db", "egress"]


def test_bot_container_is_hardened():
    bot = compose()["services"]["bot"]
    assert bot["read_only"] is True
    assert "no-new-privileges:true" in bot["security_opt"]


def test_settings_ignore_empty_env(monkeypatch):
    from czekachiko.config import Settings

    monkeypatch.setenv("ADMIN_TG_ID", "")
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u:p@h/d", _env_file=None)
    assert s.admin_tg_id is None


def test_migrations_ship_inside_package():
    assert (ROOT / "src/czekachiko/migrations/env.py").exists()
