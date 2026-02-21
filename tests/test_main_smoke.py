from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import cli as entrypoint
from app.usecases.process_cycle import CycleStats
from tests.main_test_harness import make_settings, patch_service_runtime


def test_run_service_auto_cleanup_once_on_run_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    probe = patch_service_runtime(
        monkeypatch=monkeypatch,
        settings=settings,
        logger_name="test.main.smoke.cleanup",
        cycle_stats=CycleStats(
            start_date="20260221",
            end_date="20260222",
            area_count=1,
        ),
        health_decision=ApiHealthDecision(incident_open=False),
    )

    result = entrypoint._run_service()

    assert result == 0
    assert probe.cleanup_calls == [(30, False, False)]
    assert probe.processor_lookback_calls == [None]


def test_run_service_sends_health_alert_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(
        tmp_path,
        health_outage_min_failed_cycles=1,
        health_outage_consecutive_failures=1,
        run_once=True,
    )
    probe = patch_service_runtime(
        monkeypatch=monkeypatch,
        settings=settings,
        logger_name="test.main.smoke.health",
        cycle_stats=CycleStats(
            start_date="20260221",
            end_date="20260222",
            area_count=1,
            area_failures=1,
            api_error_counts={"timeout": 1},
            last_api_error="timeout",
        ),
        health_decision=ApiHealthDecision(
            incident_open=True,
            event="outage_detected",
            should_notify=True,
            outage_window_cycles=1,
            outage_window_failed_cycles=1,
            outage_window_fail_ratio=1.0,
            consecutive_severe_failures=1,
            representative_error="timeout",
        ),
    )

    result = entrypoint._run_service()

    assert result == 0
    assert len(probe.notifier_messages) == 1
    assert probe.notifier_messages[0].startswith("[API 장애 감지]")


def test_run_service_runs_backfill_after_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(
        tmp_path,
        run_once=True,
        lookback_days=0,
        health_recovery_backfill_max_days=3,
    )
    probe = patch_service_runtime(
        monkeypatch=monkeypatch,
        settings=settings,
        logger_name="test.main.smoke.backfill",
        cycle_stats=CycleStats(
            start_date="20260221",
            end_date="20260222",
            area_count=1,
        ),
        health_decision=ApiHealthDecision(
            incident_open=False,
            event="recovered",
            should_notify=False,
            incident_duration_sec=90000,
        ),
    )

    result = entrypoint._run_service()

    assert result == 0
    assert probe.processor_lookback_calls == [None, 2]


def test_run_service_uses_sqlite_state_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(
        tmp_path,
        state_repository_type="sqlite",
        sqlite_state_file=tmp_path / "state.db",
    )
    probe = patch_service_runtime(
        monkeypatch=monkeypatch,
        settings=settings,
        logger_name="test.main.smoke.sqlite",
        cycle_stats=CycleStats(
            start_date="20260221",
            end_date="20260222",
            area_count=1,
        ),
        health_decision=ApiHealthDecision(incident_open=False),
    )

    result = entrypoint._run_service()

    assert result == 0
    assert probe.sqlite_repo_file == settings.sqlite_state_file
