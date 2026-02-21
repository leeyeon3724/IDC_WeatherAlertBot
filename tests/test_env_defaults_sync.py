from __future__ import annotations

from pathlib import Path

from scripts.check_env_defaults_sync import build_report


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _seed_base_files(repo_root: Path) -> None:
    _write(
        repo_root / ".env.example",
        """
        SERVICE_API_KEY=prod-key
        SERVICE_HOOK_URL=https://hook.example/prod
        RUN_ONCE=false
        DRY_RUN=false
        LOG_LEVEL=INFO
        AREA_MAX_WORKERS=1
        LOOKBACK_DAYS=0
        """,
    )
    _write(
        repo_root / ".env.live-e2e.example",
        """
        ENABLE_LIVE_E2E=true
        SERVICE_API_KEY=test-key
        SERVICE_HOOK_URL=https://hook.example/test
        RUN_ONCE=true
        DRY_RUN=false
        LOG_LEVEL=INFO
        AREA_MAX_WORKERS=1
        LOOKBACK_DAYS=0
        """,
    )
    _write(
        repo_root / "docker-compose.yml",
        """
        services:
          weather-alert-bot:
            environment:
              DRY_RUN: "false"
              RUN_ONCE: "false"
              AREA_MAX_WORKERS: "2"
              LOOKBACK_DAYS: "0"
        """,
    )


def test_build_report_passes_for_allowlisted_differences(tmp_path: Path) -> None:
    _seed_base_files(tmp_path)

    report = build_report(tmp_path)

    assert report["passed"] is True
    assert report["live_e2e_disallowed_diffs"] == []
    assert report["docker_compose_disallowed_diffs"] == []
    assert report["docker_compose_unknown_keys"] == []


def test_build_report_detects_non_allowlisted_diff_and_unknown_compose_key(tmp_path: Path) -> None:
    _seed_base_files(tmp_path)
    _write(
        tmp_path / ".env.live-e2e.example",
        """
        ENABLE_LIVE_E2E=true
        SERVICE_API_KEY=test-key
        SERVICE_HOOK_URL=https://hook.example/test
        RUN_ONCE=true
        DRY_RUN=true
        LOG_LEVEL=DEBUG
        AREA_MAX_WORKERS=1
        LOOKBACK_DAYS=0
        """,
    )
    _write(
        tmp_path / "docker-compose.yml",
        """
        services:
          weather-alert-bot:
            environment:
              DRY_RUN: "true"
              RUN_ONCE: "false"
              AREA_MAX_WORKERS: "2"
              LOOKBACK_DAYS: "0"
              UNKNOWN_KEY: "x"
        """,
    )

    report = build_report(tmp_path)

    assert report["passed"] is False
    assert report["docker_compose_unknown_keys"] == ["UNKNOWN_KEY"]

    live_diffs = report["live_e2e_disallowed_diffs"]
    assert live_diffs == [{"key": "LOG_LEVEL", "left": "INFO", "right": "DEBUG"}]

    compose_diffs = report["docker_compose_disallowed_diffs"]
    assert compose_diffs == [{"key": "DRY_RUN", "left": "false", "right": "true"}]
