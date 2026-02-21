from __future__ import annotations

import json
import textwrap
from pathlib import Path

from scripts.canary_report import build_report


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_build_report_passes_for_successful_run(tmp_path: Path) -> None:
    log_file = tmp_path / "canary.log"
    webhook_probe_file = tmp_path / "webhook_probe.json"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"startup.ready"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:02] [INFO] weather_alert_bot.weather_api {"event":"area.fetch.summary"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot {"event":"cycle.complete"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot {"event":"shutdown.run_once_complete"}
        """,
    )
    webhook_probe_file.write_text(
        json.dumps({"passed": True, "error": ""}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = build_report(
        log_file=log_file,
        service_exit_code=0,
        webhook_probe_file=webhook_probe_file,
    )

    assert report["passed"] is True
    assert report["missing_required_events"] == []
    assert report["failure_event_counts"] == {}
    assert report["area_fetch_summary_count"] == 1


def test_build_report_fails_for_failure_event_and_webhook_error(tmp_path: Path) -> None:
    log_file = tmp_path / "canary.log"
    webhook_probe_file = tmp_path / "webhook_probe.json"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"startup.ready"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"cycle.start"}
        [2026-02-21 10:00:02] [ERROR] weather_alert_bot.processor
        {"event":"area.failed","error_code":"timeout"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot {"event":"cycle.complete"}
        [2026-02-21 10:00:03] [INFO] weather_alert_bot {"event":"shutdown.run_once_complete"}
        """,
    )
    webhook_probe_file.write_text(
        json.dumps({"passed": False, "error": "webhook timeout"}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = build_report(
        log_file=log_file,
        service_exit_code=0,
        webhook_probe_file=webhook_probe_file,
    )

    assert report["passed"] is False
    assert report["webhook_probe_passed"] is False
    assert report["failure_event_counts"] == {"area.failed": 1}


def test_build_report_fails_for_missing_required_events(tmp_path: Path) -> None:
    log_file = tmp_path / "canary.log"
    webhook_probe_file = tmp_path / "webhook_probe.json"
    _write(
        log_file,
        """
        [2026-02-21 10:00:00] [INFO] weather_alert_bot {"event":"startup.ready"}
        [2026-02-21 10:00:01] [INFO] weather_alert_bot {"event":"cycle.start"}
        """,
    )
    webhook_probe_file.write_text(
        json.dumps({"passed": True, "error": ""}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = build_report(
        log_file=log_file,
        service_exit_code=1,
        webhook_probe_file=webhook_probe_file,
    )

    assert report["passed"] is False
    assert "cycle.complete" in report["missing_required_events"]
    assert "shutdown.run_once_complete" in report["missing_required_events"]
