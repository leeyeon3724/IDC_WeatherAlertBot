from __future__ import annotations

from app.domain.health import ApiHealthDecision


def build_health_notification_message(decision: ApiHealthDecision) -> str:
    if decision.event == "outage_detected":
        return _build_outage_detected_message(decision)
    if decision.event == "outage_heartbeat":
        return _build_outage_heartbeat_message(decision)
    if decision.event == "recovered":
        return _build_recovered_message(decision)
    return ""


def _build_outage_detected_message(decision: ApiHealthDecision) -> str:
    return (
        "[API 장애 감지]\n"
        f"- 10분 장애비율: {_ratio_percent(decision.outage_window_fail_ratio)}\n"
        f"- 실패 사이클: {decision.outage_window_failed_cycles}/{decision.outage_window_cycles}\n"
        f"- 연속 심각 실패: {decision.consecutive_severe_failures}회\n"
        f"- 대표 오류: {decision.representative_error or 'N/A'}\n"
        "- 알림 정책에 따라 장애 상태를 지속 추적합니다."
    )


def _build_outage_heartbeat_message(decision: ApiHealthDecision) -> str:
    return (
        "[API 장애 지속]\n"
        f"- 장애 지속 시간: {_format_duration(decision.incident_duration_sec)}\n"
        "- 누적 실패/전체 사이클: "
        f"{decision.incident_failed_cycles}/{decision.incident_total_cycles}\n"
        f"- 최근 10분 장애비율: {_ratio_percent(decision.outage_window_fail_ratio)}\n"
        f"- 대표 오류: {decision.representative_error or 'N/A'}"
    )


def _build_recovered_message(decision: ApiHealthDecision) -> str:
    return (
        "[API 복구]\n"
        f"- 장애 지속 시간: {_format_duration(decision.incident_duration_sec)}\n"
        f"- 최근 안정 구간 실패비율: {_ratio_percent(decision.recovery_window_fail_ratio)}\n"
        f"- 연속 안정 사이클: {decision.consecutive_stable_successes}회\n"
        "- 기준 충족으로 장애 상태를 종료했습니다."
    )


def _ratio_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_duration(total_seconds: int) -> str:
    seconds = max(total_seconds, 0)
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours > 0:
        return f"{hours}시간 {minutes}분"
    return f"{minutes}분"
