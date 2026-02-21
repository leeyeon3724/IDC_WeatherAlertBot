from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

REQUIRED_EVENTS = (
    "startup.ready",
    "cycle.start",
    "cycle.complete",
    "shutdown.run_once_complete",
)

FAILURE_EVENTS = (
    "startup.invalid_config",
    "shutdown.unexpected_error",
    "area.failed",
    "notification.final_failure",
    "state.read_failed",
    "state.persist_failed",
)


def parse_log_events(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("event"), str):
            events.append(payload)
    return events


def load_webhook_probe_result(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"passed": False, "error": f"missing file: {path}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"passed": False, "error": f"invalid json: {path}"}

    if not isinstance(payload, dict):
        return {"passed": False, "error": f"invalid payload type: {type(payload).__name__}"}
    passed = bool(payload.get("passed", False))
    error = str(payload.get("error", "")).strip()
    return {"passed": passed, "error": error}


def build_report(
    *,
    log_file: Path,
    service_exit_code: int,
    webhook_probe_file: Path,
) -> dict[str, Any]:
    log_events = parse_log_events(log_file)
    event_counts: Counter[str] = Counter(
        str(payload["event"]).strip() for payload in log_events if payload.get("event")
    )
    missing_required = [event for event in REQUIRED_EVENTS if event_counts[event] == 0]
    failure_counts = {
        event: event_counts[event] for event in FAILURE_EVENTS if event_counts[event] > 0
    }
    webhook_probe = load_webhook_probe_result(webhook_probe_file)

    passed = (
        service_exit_code == 0
        and webhook_probe["passed"]
        and not missing_required
        and not failure_counts
    )
    return {
        "passed": passed,
        "service_exit_code": service_exit_code,
        "webhook_probe_passed": webhook_probe["passed"],
        "webhook_probe_error": webhook_probe["error"],
        "total_events": len(log_events),
        "required_events": list(REQUIRED_EVENTS),
        "missing_required_events": missing_required,
        "failure_event_counts": failure_counts,
        "notification_sent_count": event_counts["notification.sent"],
        "area_fetch_summary_count": event_counts["area.fetch.summary"],
        "event_counts": dict(sorted(event_counts.items())),
    }


def render_markdown(report: dict[str, Any]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Canary Report",
        "",
        f"- status: `{status}`",
        f"- service_exit_code: `{report['service_exit_code']}`",
        f"- webhook_probe_passed: `{report['webhook_probe_passed']}`",
        f"- webhook_probe_error: `{report['webhook_probe_error']}`",
        f"- total_events: `{report['total_events']}`",
        f"- missing_required_events: `{report['missing_required_events']}`",
        f"- failure_event_counts: `{report['failure_event_counts']}`",
        f"- notification_sent_count: `{report['notification_sent_count']}`",
        f"- area_fetch_summary_count: `{report['area_fetch_summary_count']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build canary run report from service log.")
    parser.add_argument(
        "--log-file",
        type=Path,
        required=True,
        help="Path to canary service log file.",
    )
    parser.add_argument(
        "--service-exit-code",
        type=int,
        required=True,
        help="Exit code from canary service command.",
    )
    parser.add_argument(
        "--webhook-probe-file",
        type=Path,
        required=True,
        help="Path to webhook probe JSON result file.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    report = build_report(
        log_file=args.log_file,
        service_exit_code=args.service_exit_code,
        webhook_probe_file=args.webhook_probe_file,
    )
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    markdown = render_markdown(report)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(markdown)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
