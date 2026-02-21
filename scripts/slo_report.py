from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

RE_TIMESTAMP = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
RE_EVENT_MARKER = re.compile(r'"event"\s*:\s*"([^"]+)"')


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * pct
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _parse_timestamp(line: str) -> datetime | None:
    match = RE_TIMESTAMP.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_log(
    log_file: Path,
) -> tuple[list[tuple[datetime | None, dict[str, Any]]], dict[str, int]]:
    if not log_file.exists():
        return [], {
            "lines_total": 0,
            "json_decode_errors": 0,
            "parsed_event_records": 0,
            "cycle_cost_marker_lines": 0,
            "cycle_cost_marker_parse_errors": 0,
            "cycle_cost_parsed_records": 0,
        }

    parsed: list[tuple[datetime | None, dict[str, Any]]] = []
    diagnostics = {
        "lines_total": 0,
        "json_decode_errors": 0,
        "parsed_event_records": 0,
        "cycle_cost_marker_lines": 0,
        "cycle_cost_marker_parse_errors": 0,
        "cycle_cost_parsed_records": 0,
    }
    for line in log_file.read_text(encoding="utf-8").splitlines():
        diagnostics["lines_total"] += 1
        marker_match = RE_EVENT_MARKER.search(line)
        marker_event = marker_match.group(1) if marker_match else None
        if marker_event == "cycle.cost.metrics":
            diagnostics["cycle_cost_marker_lines"] += 1

        start = line.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(line[start:])
        except json.JSONDecodeError:
            diagnostics["json_decode_errors"] += 1
            if marker_event == "cycle.cost.metrics":
                diagnostics["cycle_cost_marker_parse_errors"] += 1
            continue
        if isinstance(payload, dict) and isinstance(payload.get("event"), str):
            parsed.append((_parse_timestamp(line), payload))
            diagnostics["parsed_event_records"] += 1
            if payload.get("event") == "cycle.cost.metrics":
                diagnostics["cycle_cost_parsed_records"] += 1
    return parsed, diagnostics


def _classify_missing_field_cause(
    *,
    cycle_cost_records: int,
    cycle_cost_marker_parse_errors: int,
) -> str:
    if cycle_cost_marker_parse_errors > 0:
        return "log_format"
    if cycle_cost_records <= 0:
        return "collection_gap"
    return "code_omission"


def build_report(
    *,
    log_file: Path,
    min_success_rate: float,
    max_failure_rate: float,
    max_p95_cycle_latency_sec: float,
    max_pending_latest: int,
) -> dict[str, Any]:
    records, diagnostics = parse_log(log_file)
    cycle_starts: list[datetime] = []
    cycle_latencies: list[float] = []

    sent_total = 0
    failure_total = 0
    attempts_total = 0
    cycle_complete_pending_latest: int | None = None
    pending_latest: int | None = None
    cycle_cost_records = 0
    cycle_cost_records_with_pending = 0
    cycle_cost_records_with_attempts = 0

    missing_field_causes: list[dict[str, Any]] = []
    fallbacks_applied: list[dict[str, Any]] = []
    data_quality_warnings: list[str] = []

    for timestamp, payload in records:
        event = str(payload.get("event"))
        if event == "cycle.start" and timestamp is not None:
            cycle_starts.append(timestamp)
        elif event == "cycle.complete" and timestamp is not None and cycle_starts:
            start = cycle_starts.pop(0)
            cycle_latencies.append(max((timestamp - start).total_seconds(), 0.0))
            pending_from_complete = _safe_int(payload.get("pending_total"))
            if pending_from_complete is not None:
                cycle_complete_pending_latest = pending_from_complete
        elif event == "notification.sent":
            sent_total += 1
        elif event == "notification.final_failure":
            failure_total += 1
        elif event == "cycle.cost.metrics":
            cycle_cost_records += 1
            attempts_value = _safe_int(payload.get("notification_attempts"))
            if attempts_value is not None:
                attempts_total += attempts_value
                cycle_cost_records_with_attempts += 1
            pending_value = _safe_int(payload.get("pending_total"))
            if pending_value is not None:
                pending_latest = pending_value
                cycle_cost_records_with_pending += 1

    if attempts_total == 0:
        attempts_cause = _classify_missing_field_cause(
            cycle_cost_records=cycle_cost_records,
            cycle_cost_marker_parse_errors=diagnostics["cycle_cost_marker_parse_errors"],
        )
        derived_attempts = sent_total + failure_total
        if derived_attempts > 0:
            attempts_total = derived_attempts
            fallbacks_applied.append(
                {
                    "field": "notification_attempts",
                    "source": "notification.sent + notification.final_failure",
                    "value": derived_attempts,
                    "cause": attempts_cause,
                }
            )
            data_quality_warnings.append(
                "notification_attempts missing from cycle.cost.metrics; "
                f"fallback applied from event counts (cause={attempts_cause})"
            )
            missing_field_causes.append(
                {
                    "field": "notification_attempts",
                    "cause": attempts_cause,
                    "resolved": True,
                }
            )
        elif cycle_cost_records_with_attempts == 0:
            missing_field_causes.append(
                {
                    "field": "notification_attempts",
                    "cause": attempts_cause,
                    "resolved": False,
                }
            )

    success_denominator = sent_total + failure_total
    success_rate = sent_total / success_denominator if success_denominator else 1.0
    failure_rate = failure_total / attempts_total if attempts_total else 0.0

    p50_latency = _percentile(cycle_latencies, 0.5)
    p95_latency = _percentile(cycle_latencies, 0.95)
    max_latency = max(cycle_latencies) if cycle_latencies else 0.0

    failed_reasons: list[str] = []
    if success_rate < min_success_rate:
        failed_reasons.append(
            "success_rate below target "
            f"({success_rate:.4f} < {min_success_rate:.4f})"
        )
    if failure_rate > max_failure_rate:
        failed_reasons.append(
            "failure_rate above target "
            f"({failure_rate:.4f} > {max_failure_rate:.4f})"
        )
    if p95_latency > max_p95_cycle_latency_sec:
        failed_reasons.append(
            "p95_cycle_latency_sec above target "
            f"({p95_latency:.3f} > {max_p95_cycle_latency_sec:.3f})"
        )
    if pending_latest is None:
        pending_cause = _classify_missing_field_cause(
            cycle_cost_records=cycle_cost_records,
            cycle_cost_marker_parse_errors=diagnostics["cycle_cost_marker_parse_errors"],
        )
        if cycle_complete_pending_latest is not None:
            pending_latest = cycle_complete_pending_latest
            fallbacks_applied.append(
                {
                    "field": "pending_total",
                    "source": "cycle.complete.pending_total",
                    "value": pending_latest,
                    "cause": pending_cause,
                }
            )
            data_quality_warnings.append(
                "pending_total missing from cycle.cost.metrics; "
                f"fallback applied from cycle.complete (cause={pending_cause})"
            )
            missing_field_causes.append(
                {
                    "field": "pending_total",
                    "cause": pending_cause,
                    "resolved": True,
                }
            )
        else:
            failed_reasons.append(
                "pending_total missing from cycle.cost.metrics "
                f"(cause={pending_cause})"
            )
            missing_field_causes.append(
                {
                    "field": "pending_total",
                    "cause": pending_cause,
                    "resolved": False,
                }
            )

    if pending_latest is None:
        pass
    elif pending_latest > max_pending_latest:
        failed_reasons.append(
            f"pending_latest above target ({pending_latest} > {max_pending_latest})"
        )

    return {
        "passed": not failed_reasons,
        "log_file": str(log_file),
        "records": len(records),
        "sent_total": sent_total,
        "failure_total": failure_total,
        "attempts_total": attempts_total,
        "success_rate": round(success_rate, 6),
        "failure_rate": round(failure_rate, 6),
        "pending_latest": pending_latest,
        "cycle_latency_count": len(cycle_latencies),
        "cycle_latency_p50_sec": round(p50_latency, 3),
        "cycle_latency_p95_sec": round(p95_latency, 3),
        "cycle_latency_max_sec": round(max_latency, 3),
        "diagnostics": diagnostics,
        "cycle_cost_records": cycle_cost_records,
        "cycle_cost_records_with_pending": cycle_cost_records_with_pending,
        "cycle_cost_records_with_attempts": cycle_cost_records_with_attempts,
        "missing_field_causes": missing_field_causes,
        "fallbacks_applied": fallbacks_applied,
        "data_quality_warnings": data_quality_warnings,
        "thresholds": {
            "min_success_rate": min_success_rate,
            "max_failure_rate": max_failure_rate,
            "max_p95_cycle_latency_sec": max_p95_cycle_latency_sec,
            "max_pending_latest": max_pending_latest,
        },
        "failed_reasons": failed_reasons,
    }


def render_markdown(report: dict[str, Any]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## SLO Report",
        "",
        f"- status: `{status}`",
        f"- records: `{report['records']}`",
        f"- sent_total: `{report['sent_total']}`",
        f"- failure_total: `{report['failure_total']}`",
        f"- attempts_total: `{report['attempts_total']}`",
        f"- success_rate: `{report['success_rate']}`",
        f"- failure_rate: `{report['failure_rate']}`",
        f"- pending_latest: `{report['pending_latest']}`",
        f"- cycle_cost_records: `{report['cycle_cost_records']}`",
        f"- cycle_cost_records_with_pending: `{report['cycle_cost_records_with_pending']}`",
        f"- cycle_cost_records_with_attempts: `{report['cycle_cost_records_with_attempts']}`",
        f"- cycle_latency_p50_sec: `{report['cycle_latency_p50_sec']}`",
        f"- cycle_latency_p95_sec: `{report['cycle_latency_p95_sec']}`",
        f"- cycle_latency_max_sec: `{report['cycle_latency_max_sec']}`",
        f"- diagnostics: `{report['diagnostics']}`",
        f"- missing_field_causes: `{report['missing_field_causes']}`",
        f"- fallbacks_applied: `{report['fallbacks_applied']}`",
        f"- data_quality_warnings: `{report['data_quality_warnings']}`",
        f"- failed_reasons: `{report['failed_reasons']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SLO report from structured service log.")
    parser.add_argument(
        "--log-file",
        type=Path,
        required=True,
        help="Path to structured service log file.",
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=0.95,
        help="Minimum success rate threshold.",
    )
    parser.add_argument(
        "--max-failure-rate",
        type=float,
        default=0.05,
        help="Maximum failure rate threshold.",
    )
    parser.add_argument(
        "--max-p95-cycle-latency-sec",
        type=float,
        default=300.0,
        help="Maximum p95 cycle latency threshold (seconds).",
    )
    parser.add_argument(
        "--max-pending-latest",
        type=int,
        default=0,
        help="Maximum allowed latest pending_total.",
    )
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    report = build_report(
        log_file=args.log_file,
        min_success_rate=args.min_success_rate,
        max_failure_rate=args.max_failure_rate,
        max_p95_cycle_latency_sec=args.max_p95_cycle_latency_sec,
        max_pending_latest=args.max_pending_latest,
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
