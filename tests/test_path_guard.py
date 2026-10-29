import subprocess
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "scripts/lib/validate-path.sh"


def run(path: str) -> int:
    return subprocess.run(["bash", str(GUARD), path], capture_output=True, timeout=5).returncode


def test_guard_rejects_parent_directories():
    assert run("/opt") == 1
    assert run("/") == 1
    assert run("/opt/vpnchic") == 1


def test_guard_accepts_project_directory():
    assert run("/opt/czekachiko") == 0
