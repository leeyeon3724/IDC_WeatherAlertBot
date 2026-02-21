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


def test_health_monitor_suggests_backoff_interval_when_incident_open(tmp_path) -> None:
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

    assert monitor.state.incident_open is True
    adjusted = monitor.suggested_cycle_interval_sec(base_interval_sec=10)
    assert adjusted >= 20


def test_health_monitor_suggested_interval_uses_multiplier_steps_and_cap(tmp_path) -> None:
    monitor = _monitor(tmp_path)
    monitor.state.incident_open = True

    monitor.state.consecutive_severe_failures = 1
    assert monitor.suggested_cycle_interval_sec(base_interval_sec=10) == 10

    monitor.state.consecutive_severe_failures = 2
    assert monitor.suggested_cycle_interval_sec(base_interval_sec=10) == 20

    monitor.state.consecutive_severe_failures = 4
    assert monitor.suggested_cycle_interval_sec(base_interval_sec=10) == 40

    monitor.state.consecutive_severe_failures = 6
    assert monitor.suggested_cycle_interval_sec(base_interval_sec=10) == 80

    monitor.state.consecutive_severe_failures = 8
    assert monitor.suggested_cycle_interval_sec(base_interval_sec=400) == 900


def test_health_monitor_short_heartbeat_policy_emits_periodic_heartbeat(tmp_path) -> None:
    state_repo = JsonHealthStateRepository(tmp_path / "health_state.json")
    policy = HealthPolicy(
        outage_window_sec=300,
        outage_fail_ratio_threshold=0.7,
        outage_min_failed_cycles=2,
        outage_consecutive_failures=2,
        recovery_window_sec=600,
        recovery_max_fail_ratio=0.1,
        recovery_consecutive_successes=3,
        heartbeat_interval_sec=60,
    )
    monitor = ApiHealthMonitor(state_repo=state_repo, policy=policy)
    base = datetime(2026, 2, 21, 9, 0, tzinfo=UTC)

    for offset in (0, 1):
        monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=4,
            error_counts={"timeout": 4},
            representative_error="timeout",
        )

    heartbeat = monitor.observe_cycle(
        now=base + timedelta(minutes=3),
        total_areas=4,
        failed_areas=4,
        error_counts={"timeout": 4},
        representative_error="timeout",
    )
    assert heartbeat.should_notify is True
    assert heartbeat.event == "outage_heartbeat"
    assert heartbeat.incident_open is True


def test_health_monitor_long_recovery_window_delays_recovery(tmp_path) -> None:
    state_repo = JsonHealthStateRepository(tmp_path / "health_state.json")
    policy = HealthPolicy(
        outage_window_sec=600,
        outage_fail_ratio_threshold=0.7,
        outage_min_failed_cycles=3,
        outage_consecutive_failures=2,
        recovery_window_sec=1800,
        recovery_max_fail_ratio=0.1,
        recovery_consecutive_successes=3,
        heartbeat_interval_sec=300,
    )
    monitor = ApiHealthMonitor(state_repo=state_repo, policy=policy)
    base = datetime(2026, 2, 21, 9, 0, tzinfo=UTC)

    for offset in (0, 1, 2):
        monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=4,
            error_counts={"timeout": 4},
            representative_error="timeout",
        )

    not_recovered = None
    for offset in (10, 11, 12):
        not_recovered = monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=0,
            error_counts={},
            representative_error=None,
        )
    assert not_recovered is not None
    assert not_recovered.incident_open is True
    assert not_recovered.should_notify is False

    recovered_events: list[object] = []
    for offset in (40, 41, 42):
        decision = monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=0,
            error_counts={},
            representative_error=None,
        )
        recovered_events.append(decision)
    recovered = next(
        (decision for decision in recovered_events if decision.event == "recovered"),
        None,
    )
    assert recovered is not None
    assert recovered.should_notify is True
    assert recovered.incident_open is False


def test_health_monitor_accumulates_incident_counts_and_resets_after_recovery(tmp_path) -> None:
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
    assert monitor.state.incident_open is True
    assert monitor.state.incident_total_cycles == 0
    assert monitor.state.incident_failed_cycles == 0

    monitor.observe_cycle(
        now=base + timedelta(minutes=3),
        total_areas=4,
        failed_areas=4,
        error_counts={"timeout": 2, "connection": 1},
        representative_error="timeout",
    )
    monitor.observe_cycle(
        now=base + timedelta(minutes=4),
        total_areas=4,
        failed_areas=4,
        error_counts={"timeout": 1},
        representative_error="timeout",
    )
    monitor.observe_cycle(
        now=base + timedelta(minutes=5),
        total_areas=4,
        failed_areas=0,
        error_counts={},
        representative_error=None,
    )

    assert monitor.state.incident_total_cycles == 3
    assert monitor.state.incident_failed_cycles == 2
    assert monitor.state.incident_error_counts == {"timeout": 3, "connection": 1}

    recovered = None
    for offset in (13, 14, 15):
        recovered = monitor.observe_cycle(
            now=base + timedelta(minutes=offset),
            total_areas=4,
            failed_areas=0,
            error_counts={},
            representative_error=None,
        )

    assert recovered is not None
    assert recovered.event == "recovered"
    assert monitor.state.incident_open is False
    assert monitor.state.incident_total_cycles == 0
    assert monitor.state.incident_failed_cycles == 0
    assert monitor.state.incident_error_counts == {}
    assert monitor.state.consecutive_severe_failures == 0


def test_health_monitor_persists_recovery_backfill_window(tmp_path) -> None:
    monitor = _monitor(tmp_path)

    assert monitor.get_recovery_backfill_window() is None
    monitor.set_recovery_backfill_window(start_date="20260218", end_date="20260221")
    assert monitor.get_recovery_backfill_window() == ("20260218", "20260221")

    reloaded = _monitor(tmp_path)
    assert reloaded.get_recovery_backfill_window() == ("20260218", "20260221")

    reloaded.set_recovery_backfill_window(start_date="20260221", end_date="20260220")
    assert reloaded.get_recovery_backfill_window() is None
