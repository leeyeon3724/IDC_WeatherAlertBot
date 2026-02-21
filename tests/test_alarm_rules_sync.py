from __future__ import annotations

import json
import textwrap
from pathlib import Path

from scripts.check_alarm_rules_sync import (
    build_report,
    evaluate_sample_alerts,
    parse_structured_log,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _operation_doc() -> str:
    return "\n".join(
        [
            "| 신호(Event) | 기본 임계값(예시) | 확인 필드 | 1차 대응 | 후속 조치 |",
            "|---|---|---|---|---|",
            (
                "| `area.failed` | 5분 합계 `>= 20` | "
                "`error_code`, `area_code`, `error` | check | fix |"
            ),
            (
                "| `notification.final_failure` | 10분 합계 `>= 5` | "
                "`attempts`, `event_id`, `error` | check | fix |"
            ),
        ]
    )


def test_build_report_passes_when_schema_matches_operation_and_payload(tmp_path: Path) -> None:
    operation_doc = tmp_path / "OPERATION.md"
    schema_file = tmp_path / "alarm_rules.json"

    _write(operation_doc, _operation_doc())
    schema_file.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "area-failed",
                        "event": "area.failed",
                        "threshold_display": "5분 합계 >= 20",
                        "fields": ["error_code", "area_code", "error"],
                    },
                    {
                        "id": "notification-final-failure",
                        "event": "notification.final_failure",
                        "threshold_display": "10분 합계 >= 5",
                        "fields": ["attempts", "event_id", "error"],
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        schema_path=schema_file,
        operation_doc_path=operation_doc,
        source_root=tmp_path,
        event_payload_contract={
            "area.failed": ["area_code", "error", "error_code"],
            "notification.final_failure": ["attempts", "event_id", "error"],
        },
    )

    assert report["passed"] is True
    assert report["missing_in_operation"] == []
    assert report["schema_field_missing_in_code"] == []


def test_build_report_detects_threshold_mismatch(tmp_path: Path) -> None:
    operation_doc = tmp_path / "OPERATION.md"
    schema_file = tmp_path / "alarm_rules.json"

    _write(operation_doc, _operation_doc())
    schema_file.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "area-failed",
                        "event": "area.failed",
                        "threshold_display": "5분 합계 >= 10",
                        "fields": ["error_code", "area_code", "error"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        schema_path=schema_file,
        operation_doc_path=operation_doc,
        source_root=tmp_path,
        event_payload_contract={"area.failed": ["area_code", "error", "error_code"]},
    )

    assert report["passed"] is False
    assert len(report["threshold_mismatches"]) == 1


def test_build_report_detects_duplicate_keys_and_missing_unknown_events(tmp_path: Path) -> None:
    operation_doc = tmp_path / "OPERATION.md"
    schema_file = tmp_path / "alarm_rules.json"

    _write(
        operation_doc,
        """
        | 신호(Event) | 기본 임계값(예시) | 확인 필드 | 1차 대응 | 후속 조치 |
        |---|---|---|---|---|
        | `area.failed` | 5분 합계 `>= 20` | `error_code`, `area_code`, `error` | check | fix |
        | `unknown.event` | 1분 합계 `>= 1` | `field` | check | fix |
        """,
    )
    schema_file.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "area-failed-1",
                        "event": "area.failed",
                        "threshold_display": "5분 합계 >= 20",
                        "fields": ["error_code", "area_code", "error"],
                    },
                    {
                        "id": "area-failed-2",
                        "event": "area.failed",
                        "threshold_display": "5분 합계 >= 20",
                        "fields": ["error_code", "area_code", "error"],
                    },
                    {
                        "id": "notification-final-failure",
                        "event": "notification.final_failure",
                        "threshold_display": "10분 합계 >= 5",
                        "fields": ["attempts", "event_id", "error"],
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        schema_path=schema_file,
        operation_doc_path=operation_doc,
        source_root=tmp_path,
        event_payload_contract={
            "area.failed": ["area_code", "error", "error_code"],
            "notification.final_failure": ["attempts", "event_id", "error"],
        },
    )

    assert report["passed"] is False
    assert report["duplicate_schema_keys"] == ["area.failed#"]
    assert report["missing_in_operation"] == ["notification.final_failure#"]
    assert report["unknown_in_operation"] == ["unknown.event#"]


def test_build_report_detects_schema_fields_missing_in_code_contract(tmp_path: Path) -> None:
    operation_doc = tmp_path / "OPERATION.md"
    schema_file = tmp_path / "alarm_rules.json"
    _write(operation_doc, _operation_doc())
    schema_file.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "area-failed",
                        "event": "area.failed",
                        "threshold_display": "5분 합계 >= 20",
                        "fields": ["error_code", "area_code", "error", "missing_field"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_report(
        schema_path=schema_file,
        operation_doc_path=operation_doc,
        source_root=tmp_path,
        event_payload_contract={"area.failed": ["area_code", "error", "error_code"]},
    )

    assert report["passed"] is False
    assert report["schema_field_missing_in_code"] == [
        {
            "key": "area.failed#",
            "event": "area.failed",
            "missing_fields": ["missing_field"],
        }
    ]


def test_parse_structured_log_ignores_invalid_json_payload_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [ERROR] weather_alert_bot {"event":"area.failed"}
        [2026-02-21 10:01:00] [ERROR] weather_alert_bot {"event":"area.failed"
        [2026-02-21 10:02:00] [INFO] weather_alert_bot no-json
        """,
    )

    records = parse_structured_log(log_file)
    assert len(records) == 1
    assert records[0][1]["event"] == "area.failed"


def test_evaluate_sample_alerts_with_sample_log(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 09:40:00] [ERROR] weather_alert_bot {"event":"area.failed"}
        [2026-02-21 10:00:00] [ERROR] weather_alert_bot {"event":"area.failed"}
        [2026-02-21 10:03:00] [ERROR] weather_alert_bot {"event":"area.failed"}
        """,
    )

    records = parse_structured_log(log_file)
    alerts = evaluate_sample_alerts(
        records=records,
        rules=[
            {
                "id": "area-failed-burst",
                "event": "area.failed",
                "eval": {"type": "count_gte", "window_sec": 300, "count": 2},
            }
        ],
    )

    assert len(alerts) == 1
    assert alerts[0]["matched"] == 2
    assert alerts[0]["triggered"] is True
