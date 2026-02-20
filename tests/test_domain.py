from __future__ import annotations

import pytest

from app.domain.message_builder import build_alert_message, build_notification
from app.domain.models import AlertEvent


def _sample_alert(**overrides: object) -> AlertEvent:
    base = {
        "area_code": "11B00000",
        "area_name": "서울",
        "warn_var": "호우",
        "warn_stress": "주의보",
        "command": "발표",
        "cancel": "정상",
        "start_time": "2026년 2월 20일 오전 9시",
        "end_time": "2026년 2월 20일 오후 6시",
        "stn_id": "109",
        "tm_fc": "202602200900",
        "tm_seq": "1",
    }
    base.update(overrides)
    return AlertEvent(**base)


def test_event_id_uses_station_identifiers() -> None:
    alert = _sample_alert()
    assert alert.event_id.startswith("event:109:202602200900:1:")


def test_event_id_fallback_is_stable() -> None:
    alert = _sample_alert(stn_id="", tm_fc="", tm_seq="")
    assert alert.event_id.startswith("fallback:")
    assert alert.event_id == _sample_alert(stn_id="", tm_fc="", tm_seq="").event_id


def test_build_message_and_notification() -> None:
    alert = _sample_alert()
    message = build_alert_message(alert)
    notification = build_notification(alert)

    assert "서울 호우주의보가 발표되었습니다." in message
    assert notification.event_id == alert.event_id
    assert notification.report_url is not None
    assert "https://www.weather.go.kr/w/special-report/list.do" in notification.report_url


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "command": "발표",
                "cancel": "정상",
                "start_time": "2026년 2월 20일 오전 9시",
                "end_time": None,
            },
            "2026년 2월 20일 오전 9시 서울 호우주의보가 발표되었습니다.",
        ),
        (
            {
                "command": "해제",
                "cancel": "정상",
                "start_time": "2026년 2월 19일 오전 9시",
                "end_time": "2026년 2월 20일 오전 9시",
            },
            "2026년 2월 20일 오전 9시 서울 호우주의보가 해제되었습니다.",
        ),
        (
            {
                "command": "해제",
                "cancel": "취소된 특보",
                "start_time": "2026년 2월 19일 오전 9시",
                "end_time": "2026년 2월 20일 오전 9시",
            },
            "2026년 2월 20일 오전 9시 해제되었던 서울 호우주의보가 취소되었습니다.",
        ),
    ],
)
def test_message_templates_snapshot(overrides: dict[str, object], expected: str) -> None:
    alert = _sample_alert(**overrides)
    assert build_alert_message(alert) == expected


def test_report_url_validation_blocks_incomplete_params() -> None:
    alert = _sample_alert(stn_id="109", tm_fc="", tm_seq="1")
    notification = build_notification(alert)
    assert notification.report_url is None
    assert notification.url_validation_error == "incomplete_report_params"


def test_report_url_validation_blocks_invalid_tm_fc() -> None:
    alert = _sample_alert(tm_fc="2026-02-200900")
    notification = build_notification(alert)
    assert notification.report_url is None
    assert notification.url_validation_error == "invalid_tm_fc"
