from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.container_healthcheck import evaluate_health_state


def _write_health_state(path: Path, recorded_at: datetime) -> None:
    payload = {
        "version": 1,
        "state": {
            "recent_cycles": [
                {
                    "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
                    "total_areas": 1,
                    "failed_areas": 0,
                    "error_counts": {},
                    "last_error": None,
                }
            ]
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_evaluate_health_state_fails_when_state_file_missing(tmp_path: Path) -> None:
    ok, reason = evaluate_health_state(
        file_path=tmp_path / "missing.json",
        now=datetime(2026, 2, 21, tzinfo=UTC),
        max_age_sec=60,
    )

    assert ok is False
    assert reason.startswith("health-state-missing")


def test_evaluate_health_state_passes_when_recent_cycle_is_fresh(tmp_path: Path) -> None:
    state_file = tmp_path / "health_state.json"
    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
    _write_health_state(state_file, now - timedelta(seconds=30))

    ok, reason = evaluate_health_state(
        file_path=state_file,
        now=now,
        max_age_sec=60,
    )

    assert ok is True
    assert reason.startswith("health-state-ok")


def test_evaluate_health_state_fails_when_recent_cycle_is_stale(tmp_path: Path) -> None:
    state_file = tmp_path / "health_state.json"
    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
    _write_health_state(state_file, now - timedelta(seconds=301))

    ok, reason = evaluate_health_state(
        file_path=state_file,
        now=now,
        max_age_sec=300,
    )

    assert ok is False
    assert reason.startswith("health-state-stale")


def test_evaluate_health_state_run_once_mode_skips_missing_file(tmp_path: Path) -> None:
    ok, reason = evaluate_health_state(
        file_path=tmp_path / "missing.json",
        now=datetime(2026, 2, 21, tzinfo=UTC),
        max_age_sec=60,
        run_once_mode=True,
    )

    assert ok is True
    assert reason.startswith("health-state-run-once-skip:file-missing")


def test_evaluate_health_state_run_once_mode_skips_stale_threshold(tmp_path: Path) -> None:
    state_file = tmp_path / "health_state.json"
    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
    _write_health_state(state_file, now - timedelta(hours=6))

    ok, reason = evaluate_health_state(
        file_path=state_file,
        now=now,
        max_age_sec=60,
        run_once_mode=True,
    )

    assert ok is True
    assert reason.startswith("health-state-run-once-skip:age=")
