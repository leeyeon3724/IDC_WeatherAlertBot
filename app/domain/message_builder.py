from __future__ import annotations

from app.domain.models import AlertEvent, AlertNotification


def _build_publish_message(alert: AlertEvent) -> str:
    time_str = alert.start_time or "특정 시간"
    return (
        f"{time_str} {alert.area_name} "
        f"{alert.warn_var}{alert.warn_stress}가 발표되었습니다."
    )


def _build_release_or_update_message(alert: AlertEvent) -> str:
    time_str = alert.end_time or alert.start_time or "특정 시간"
    return (
        f"{time_str} {alert.area_name} "
        f"{alert.warn_var}{alert.warn_stress}가 {alert.command}되었습니다."
    )


def _build_cancelled_message(alert: AlertEvent) -> str:
    time_str = alert.end_time or alert.start_time or "특정 시간"
    return (
        f"{time_str} {alert.command}되었던 "
        f"{alert.area_name} {alert.warn_var}{alert.warn_stress}가 취소되었습니다."
    )


def build_alert_message(alert: AlertEvent) -> str:
    if alert.cancel != "정상":
        return _build_cancelled_message(alert)
    if alert.command == "발표":
        return _build_publish_message(alert)
    return _build_release_or_update_message(alert)


def build_notification(alert: AlertEvent) -> AlertNotification:
    _, validation_error = alert.validate_report_params()
    return AlertNotification(
        event_id=alert.event_id,
        area_code=alert.area_code,
        message=build_alert_message(alert),
        report_url=alert.report_url,
        url_validation_error=validation_error,
    )
