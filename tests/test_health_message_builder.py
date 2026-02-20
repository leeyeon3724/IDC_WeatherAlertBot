from __future__ import annotations

from app.domain.health import ApiHealthDecision
from app.domain.health_message_builder import build_health_notification_message


def test_health_message_builder_outage_detected() -> None:
    message = build_health_notification_message(
        ApiHealthDecision(
            incident_open=True,
            event="outage_detected",
            should_notify=True,
            outage_window_cycles=7,
            outage_window_failed_cycles=6,
            outage_window_fail_ratio=0.8,
            consecutive_severe_failures=4,
            representative_error="timeout",
        )
    )
    assert message.startswith("[API 장애 감지]")
    assert "80.0%" in message


def test_health_message_builder_outage_heartbeat() -> None:
    message = build_health_notification_message(
        ApiHealthDecision(
            incident_open=True,
            event="outage_heartbeat",
            should_notify=True,
            outage_window_fail_ratio=0.9,
            incident_duration_sec=5400,
            incident_total_cycles=20,
            incident_failed_cycles=18,
            representative_error="connection reset",
        )
    )
    assert message.startswith("[API 장애 지속]")
    assert "1시간" in message


def test_health_message_builder_recovered() -> None:
    message = build_health_notification_message(
        ApiHealthDecision(
            incident_open=False,
            event="recovered",
            should_notify=True,
            recovery_window_fail_ratio=0.0,
            incident_duration_sec=1800,
            consecutive_stable_successes=8,
        )
    )
    assert message.startswith("[API 복구]")
    assert "30분" in message
