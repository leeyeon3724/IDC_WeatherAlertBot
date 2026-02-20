from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.health import HealthPolicy
from app.repositories.health_state_repo import JsonHealthStateRepository
from app.usecases.health_monitor import ApiHealthMonitor


def _monitor(tmp_path) -> ApiHealthMonitor:
    state_repo = JsonHealthStateRepository(tmp_path / "health_state.json")
    policy = HealthPolicy(
        outage_window_sec=600,
        outage_fail_ratio_threshold=0.7,
        outage_min_failed_cycles=3,
        outage_consecutive_failures=2,
        recovery_window_sec=600,
        recovery_max_fail_ratio=0.1,
        recovery_consecutive_successes=3,
        heartbeat_interval_sec=300,
    )
    return ApiHealthMonitor(state_repo=state_repo, policy=policy)


def test_health_monitor_ignores_transient_failure(tmp_path) -> None:
    monitor = _monitor(tmp_path)
    now = datetime(2026, 2, 21, 9, 0, tzinfo=UTC)

    first = monitor.observe_cycle(
        now=now,
        total_areas=4,
        failed_areas=4,
        error_counts={"timeout": 4},
        representative_error="timeout",
    )
    second = monitor.observe_cycle(
        now=now + timedelta(minutes=1),
        total_areas=4,
        failed_areas=0,
        error_counts={},
        representative_error=None,
    )

    assert first.should_notify is False
    assert second.should_notify is False
    assert second.incident_open is False


def test_health_monitor_detects_outage_and_sends_heartbeat(tmp_path) -> None:
    monitor = _monitor(tmp_path)
    base = datetime(2026, 2, 21, 9, 0, tzinfo=UTC)

    decision = None
    for offset in (0, 1, 2):
        decision = monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=4,
            error_counts={"timeout": 4},
            representative_error="timeout",
        )
    assert decision is not None
    assert decision.should_notify is True
    assert decision.event == "outage_detected"
    assert decision.incident_open is True

    heartbeat = monitor.observe_cycle(
        now=base + timedelta(minutes=8),
        total_areas=4,
        failed_areas=4,
        error_counts={"timeout": 4},
        representative_error="timeout",
    )
    assert heartbeat.should_notify is True
    assert heartbeat.event == "outage_heartbeat"
    assert heartbeat.incident_open is True


def test_health_monitor_sends_recovery_after_stable_window(tmp_path) -> None:
    monitor = _monitor(tmp_path)
    base = datetime(2026, 2, 21, 9, 0, tzinfo=UTC)

    for offset in (0, 1, 2):
        monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=4,
            error_counts={"timeout": 4},
            representative_error="timeout",
        )

    decision = None
    for offset in (13, 14, 15):
        decision = monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=0,
            error_counts={},
            representative_error=None,
        )
    assert decision is not None
    assert decision.should_notify is True
    assert decision.event == "recovered"
    assert decision.incident_open is False
