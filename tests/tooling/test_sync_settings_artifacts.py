from __future__ import annotations

from pathlib import Path

from scripts.sync_settings_artifacts import (
    build_settings_env_defaults,
    render_env_example,
    render_live_e2e_example,
    sync_settings_artifacts,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_settings_env_defaults_contains_expected_keys() -> None:
    defaults = build_settings_env_defaults()
    assert defaults["STATE_REPOSITORY_TYPE"] == "sqlite"
    assert defaults["SHUTDOWN_TIMEOUT_SEC"] == "30"
    assert defaults["ALERT_RULES_FILE"] == "./config/alert_rules.v1.json"


def test_render_env_example_uses_required_placeholders() -> None:
    defaults = build_settings_env_defaults()
    rendered = render_env_example(defaults)
    assert "SERVICE_API_KEY=YOUR_SERVICE_KEY" in rendered
    assert "SERVICE_HOOK_URL=https://hook.dooray.com/services/your/path" in rendered
    assert "SHUTDOWN_TIMEOUT_SEC=30" in rendered


def test_render_live_e2e_example_applies_runtime_overrides() -> None:
    defaults = build_settings_env_defaults()
    rendered = render_live_e2e_example(defaults)
    assert "ENABLE_LIVE_E2E=true" in rendered
    assert "CYCLE_INTERVAL_SEC=0" in rendered
    assert "AREA_INTERVAL_SEC=0" in rendered


def test_sync_settings_artifacts_check_and_write_modes(tmp_path: Path) -> None:
    defaults = build_settings_env_defaults()

    _write(tmp_path / ".env.example", render_env_example(defaults))
    _write(tmp_path / ".env.live-e2e.example", render_live_e2e_example(defaults))

    assert sync_settings_artifacts(repo_root=tmp_path, write=False) == 0

    _write(
        tmp_path / ".env.example",
        render_env_example(defaults).replace("SHUTDOWN_TIMEOUT_SEC=30", "SHUTDOWN_TIMEOUT_SEC=31"),
    )
    assert sync_settings_artifacts(repo_root=tmp_path, write=False) == 1
    assert sync_settings_artifacts(repo_root=tmp_path, write=True) == 0
    assert "SHUTDOWN_TIMEOUT_SEC=30" in (tmp_path / ".env.example").read_text(encoding="utf-8")
