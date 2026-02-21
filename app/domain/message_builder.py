from __future__ import annotations

from app.domain.alert_rules import AlertMessageRules, default_alert_rules
from app.domain.models import AlertEvent, AlertNotification

DEFAULT_MESSAGE_RULES = default_alert_rules().message_rules


def _build_publish_message(alert: AlertEvent, rules: AlertMessageRules) -> str:
    time_str = alert.start_time or "특정 시간"
    return rules.publish_template.format(
        time=time_str,
        area_name=alert.area_name,
        warn_var=alert.warn_var,
        warn_stress=alert.warn_stress,
        command=alert.command,
    )


def _build_release_or_update_message(alert: AlertEvent, rules: AlertMessageRules) -> str:
    time_str = alert.end_time or alert.start_time or "특정 시간"
    return rules.release_or_update_template.format(
        time=time_str,
        area_name=alert.area_name,
        warn_var=alert.warn_var,
        warn_stress=alert.warn_stress,
        command=alert.command,
    )


def _build_cancelled_message(alert: AlertEvent, rules: AlertMessageRules) -> str:
    time_str = alert.end_time or alert.start_time or "특정 시간"
    return rules.cancelled_template.format(
        time=time_str,
        area_name=alert.area_name,
        warn_var=alert.warn_var,
        warn_stress=alert.warn_stress,
        command=alert.command,
    )


def build_alert_message(
    alert: AlertEvent,
    *,
    rules: AlertMessageRules | None = None,
) -> str:
    message_rules = rules or DEFAULT_MESSAGE_RULES
    if alert.cancel != message_rules.normal_cancel_value:
        return _build_cancelled_message(alert, message_rules)
    if alert.command == message_rules.publish_command_value:
        return _build_publish_message(alert, message_rules)
    return _build_release_or_update_message(alert, message_rules)


def build_notification(
    alert: AlertEvent,
    *,
    rules: AlertMessageRules | None = None,
) -> AlertNotification:
    _, validation_error = alert.validate_report_params()
    return AlertNotification(
        event_id=alert.event_id,
        area_code=alert.area_code,
        message=build_alert_message(alert, rules=rules),
        report_url=alert.report_url,
        url_validation_error=validation_error,
    )
