from __future__ import annotations

from app.domain.models import AlertEvent, AlertNotification


def build_alert_message(alert: AlertEvent) -> str:
    time_str = alert.start_time if alert.command == "발표" else alert.end_time
    if alert.cancel == "정상":
        if time_str:
            return (
                f"{time_str} {alert.area_name} "
                f"{alert.warn_var}{alert.warn_stress}가 {alert.command}되었습니다."
            )
        return (
            f"{alert.start_time} {alert.area_name} "
            f"{alert.warn_var}{alert.warn_stress}로 {alert.command}되었습니다."
        )

    time_str = time_str or "특정 시간"
    return (
        f"{time_str} {alert.command}되었던 "
        f"{alert.area_name} {alert.warn_var}{alert.warn_stress}가 취소되었습니다."
    )


def build_notification(alert: AlertEvent) -> AlertNotification:
    return AlertNotification(
        event_id=alert.event_id,
        area_code=alert.area_code,
        message=build_alert_message(alert),
        report_url=alert.report_url,
    )

