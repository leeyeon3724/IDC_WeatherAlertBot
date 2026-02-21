from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.slo_report import build_report


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_build_report_passes_for_healthy_log(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"notification.sent","event_id":"a"}
        [2026-02-21 10:00:02] [INFO] weather_alert_bot {"event":"cycle.complete"}
        [2026-02-21 10:00:02] [INFO] weather_alert_bot
        {"event":"cycle.cost.metrics","notification_attempts":1,"pending_total":0}
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=1.0,
        max_failure_rate=0.0,
        max_p95_cycle_latency_sec=10,
        max_pending_latest=0,
    )

    assert report["passed"] is True
    assert report["success_rate"] == 1.0
    assert report["failure_rate"] == 0.0
    assert report["pending_latest"] == 0


def test_build_report_fails_for_failure_rate_and_pending(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:01] [ERROR] weather_alert_bot
        {"event":"notification.final_failure","event_id":"a"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot {"event":"cycle.complete"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot
        {"event":"cycle.cost.metrics","notification_attempts":1,"pending_total":2}
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=0.9,
        max_failure_rate=0.0,
        max_p95_cycle_latency_sec=10,
        max_pending_latest=0,
    )

    assert report["passed"] is False
    assert any("failure_rate above target" in reason for reason in report["failed_reasons"])
    assert any("pending_latest above target" in reason for reason in report["failed_reasons"])


def test_build_report_fails_when_pending_metric_missing(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"notification.sent","event_id":"a"}
        [2026-02-21 10:00:02] [INFO] weather_alert_bot {"event":"cycle.complete"}
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=0.9,
        max_failure_rate=0.1,
        max_p95_cycle_latency_sec=10,
        max_pending_latest=0,
    )

    assert report["passed"] is False
    assert any(
        "pending_total missing from cycle.cost.metrics (cause=collection_gap)" == reason
        for reason in report["failed_reasons"]
    )


def test_build_report_applies_pending_fallback_with_code_omission_cause(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"notification.sent","event_id":"a"}
        [2026-02-21 10:00:02] [INFO] weather_alert_bot {"event":"cycle.complete","pending_total":0}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot
        {"event":"cycle.cost.metrics","notification_attempts":1}
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=1.0,
        max_failure_rate=0.0,
        max_p95_cycle_latency_sec=10,
        max_pending_latest=0,
    )

    assert report["passed"] is True
    assert report["pending_latest"] == 0
    assert any(
        item["field"] == "pending_total" and item["cause"] == "code_omission"
        for item in report["fallbacks_applied"]
    )


def test_build_report_classifies_log_format_when_cycle_cost_is_malformed(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"notification.sent","event_id":"a"}
        [2026-02-21 10:00:02] [INFO] weather_alert_bot {"event":"cycle.complete"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot
        {"event":"cycle.cost.metrics","notification_attempts":1
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=0.9,
        max_failure_rate=0.1,
        max_p95_cycle_latency_sec=10,
        max_pending_latest=0,
    )

    assert report["passed"] is False
    assert (
        "pending_total missing from cycle.cost.metrics (cause=log_format)"
        in report["failed_reasons"]
    )


def test_build_report_fails_when_p95_cycle_latency_exceeds_target(tmp_path: Path) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:20] [INFO] weather_alert_bot {"event":"cycle.complete","pending_total":0}
        [2026-02-21 10:00:21] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:22] [INFO] weather_alert_bot {"event":"cycle.complete","pending_total":0}
        [2026-02-21 10:00:23] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:24] [INFO] weather_alert_bot {"event":"cycle.complete","pending_total":0}
        [2026-02-21 10:00:24] [INFO] weather_alert_bot
        {"event":"cycle.cost.metrics","notification_attempts":0,"pending_total":0}
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=0.0,
        max_failure_rate=1.0,
        max_p95_cycle_latency_sec=5,
        max_pending_latest=0,
    )

    assert report["passed"] is False
    assert any("p95_cycle_latency_sec above target" in reason for reason in report["failed_reasons"])


def test_build_report_marks_unresolved_attempts_fallback_when_attempt_metric_missing(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "service.log"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"cycle.complete","pending_total":0}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"cycle.cost.metrics","pending_total":0}
        """,
    )

    report = build_report(
        log_file=log_file,
        min_success_rate=0.0,
        max_failure_rate=1.0,
        max_p95_cycle_latency_sec=60,
        max_pending_latest=0,
    )

    assert report["passed"] is True
    assert any(
        item["field"] == "notification_attempts"
        and item["resolved"] is False
        and item["cause"] == "code_omission"
        for item in report["missing_field_causes"]
    )
