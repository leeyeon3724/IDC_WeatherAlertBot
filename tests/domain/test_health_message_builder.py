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
    lines = message.splitlines()
    assert lines[0] == "[API 장애 감지]"
    assert lines[1] == "- 10분 장애비율: 80.0%"
    assert lines[2] == "- 실패 사이클: 6/7"
    assert lines[3] == "- 연속 심각 실패: 4회"
    assert lines[4] == "- 대표 오류: timeout"


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
    lines = message.splitlines()
    assert lines[0] == "[API 장애 지속]"
    assert lines[1] == "- 장애 지속 시간: 1시간 30분"
    assert lines[2] == "- 누적 실패/전체 사이클: 18/20"
    assert lines[3] == "- 최근 10분 장애비율: 90.0%"
    assert lines[4] == "- 대표 오류: connection reset"


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
    lines = message.splitlines()
    assert lines[0] == "[API 복구]"
    assert lines[1] == "- 장애 지속 시간: 30분"
    assert lines[2] == "- 최근 안정 구간 실패비율: 0.0%"
    assert lines[3] == "- 연속 안정 사이클: 8회"


def test_health_message_builder_returns_empty_for_unsupported_event() -> None:
    message = build_health_notification_message(
        ApiHealthDecision(incident_open=False, event="unknown", should_notify=True)
    )
    assert message == ""


def test_health_message_builder_formats_zero_minute_duration() -> None:
    message = build_health_notification_message(
        ApiHealthDecision(
            incident_open=True,
            event="outage_heartbeat",
            should_notify=True,
            incident_duration_sec=0,
            incident_total_cycles=2,
            incident_failed_cycles=2,
            outage_window_fail_ratio=1.0,
            representative_error=None,
        )
    )
    assert "- 장애 지속 시간: 0분" in message
    assert "- 대표 오류: N/A" in message


def test_health_message_builder_formats_hour_transition_duration() -> None:
    message = build_health_notification_message(
        ApiHealthDecision(
            incident_open=False,
            event="recovered",
            should_notify=True,
            recovery_window_fail_ratio=0.05,
            incident_duration_sec=3660,
            consecutive_stable_successes=9,
        )
    )
    assert "- 장애 지속 시간: 1시간 1분" in message
