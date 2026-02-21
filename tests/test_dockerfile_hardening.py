from __future__ import annotations

from pathlib import Path


def _dockerfile_lines() -> list[str]:
    return Path("Dockerfile").read_text(encoding="utf-8").splitlines()


def test_dockerfile_runs_as_non_root_user() -> None:
    user_lines = [line.strip() for line in _dockerfile_lines() if line.strip().startswith("USER ")]
    assert user_lines, "Dockerfile must declare a runtime user."
    assert user_lines[-1] == "USER app"


def test_dockerfile_prepares_writable_data_dir_for_runtime_user() -> None:
    lines = _dockerfile_lines()
    assert any("mkdir -p /app/data" in line for line in lines)
    assert any("chown -R app:app /app" in line for line in lines)
