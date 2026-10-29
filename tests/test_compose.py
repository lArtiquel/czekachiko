import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LIMITS = ("mem_limit", "cpus", "pids_limit", "logging")


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def services():
    return compose()["services"]


def test_compose_has_no_published_ports_and_every_service_is_limited():
    for name, svc in services().items():
        assert "ports" not in svc, name
        assert "expose" not in svc, name
        assert "network_mode" not in svc, name
        for key in LIMITS:
            assert key in svc, f"{name} missing {key}"
        assert "no-new-privileges:true" in svc["security_opt"], name


def test_networks_isolate_db_and_edge():
    """db and edge are internal: only bot and tunnel reach the internet, through egress.
    The api talks to Postgres and to the tunnel, nothing else."""
    c = compose()
    assert c["networks"]["db"]["internal"] is True
    assert c["networks"]["edge"]["internal"] is True
    assert c["networks"]["egress"].get("internal") is not True
    nets = {name: sorted(svc["networks"]) for name, svc in c["services"].items()}
    assert nets == {
        "db": ["db"],
        "bot": ["db", "egress"],
        "api": ["db", "edge"],
        "tunnel": ["edge", "egress"],
    }


def test_bot_container_is_hardened():
    bot = services()["bot"]
    assert bot["read_only"] is True
    assert "no-new-privileges:true" in bot["security_opt"]


def test_api_service():
    s = services()
    api = s["api"]
    assert api["build"] == s["bot"]["build"]
    assert api["command"] == ["python", "-m", "czekachiko.api"]
    assert api["env_file"] == s["bot"]["env_file"]
    assert api["read_only"] is True and api["tmpfs"] == ["/tmp"]
    assert (api["mem_limit"], api["cpus"], api["pids_limit"]) == ("320m", 0.5, 128)
    assert api["restart"] == "unless-stopped"
    assert "/api/health" in " ".join(api["healthcheck"]["test"])
    assert "volumes" not in api  # no access to the calendar key


def test_tunnel_service():
    tunnel = services()["tunnel"]
    image, _, tag = tunnel["image"].partition(":")
    assert image == "cloudflare/cloudflared" and tag[:4].isdigit()  # pinned, never latest
    assert tunnel["command"] == ["tunnel", "--no-autoupdate", "run", "--url", "http://api:8080"]
    assert tunnel["env_file"] == ["tunnel.env"]
    assert "environment" not in tunnel
    assert (tunnel["mem_limit"], tunnel["cpus"]) == ("128m", 0.3)
    assert tunnel["restart"] == "unless-stopped"


def test_tunnel_token_reaches_only_the_tunnel():
    for name, svc in services().items():
        if name != "tunnel":
            assert "tunnel.env" not in svc.get("env_file", []), name
    assert "TUNNEL" not in (ROOT / ".env.example").read_text()
    assert "TUNNEL_TOKEN=\n" in (ROOT / "tunnel.env.example").read_text()
    for ignore in (".gitignore", ".dockerignore"):
        assert "tunnel.env" in (ROOT / ignore).read_text().split(), ignore


def test_deploy_script_ships_tunnel_env_and_waits_for_api():
    script = (ROOT / "scripts/deploy.sh").read_text()
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts/deploy.sh")]).returncode == 0
    assert "--exclude tunnel.env" in script
    assert 'scp -q tunnel.env "$DEPLOY_HOST:$DEPLOY_PATH/tunnel.env"' in script
    assert "chmod 600 .env tunnel.env" in script
    assert "[[ -f tunnel.env ]] || : > tunnel.env" in script
    assert "czekachiko-api-1" in script and "healthy" in script
    assert "grep -v '^/czekachiko-'" in script  # other projects' containers stay watched


def test_settings_ignore_empty_env(monkeypatch):
    from czekachiko.config import Settings

    monkeypatch.setenv("ADMIN_TG_ID", "")
    s = Settings(bot_token="x", database_url="postgresql+asyncpg://u:p@h/d", _env_file=None)
    assert s.admin_tg_id is None


def test_migrations_ship_inside_package():
    assert (ROOT / "src/czekachiko/migrations/env.py").exists()
