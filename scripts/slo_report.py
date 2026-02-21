from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

RE_TIMESTAMP = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


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


def parse_log(log_file: Path) -> list[tuple[datetime | None, dict[str, Any]]]:
    if not log_file.exists():
        return []

    parsed: list[tuple[datetime | None, dict[str, Any]]] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("event"), str):
            parsed.append((_parse_timestamp(line), payload))
    return parsed


def build_report(
    *,
    log_file: Path,
    min_success_rate: float,
    max_failure_rate: float,
    max_p95_cycle_latency_sec: float,
    max_pending_latest: int,
) -> dict[str, Any]:
    records = parse_log(log_file)
    cycle_starts: list[datetime] = []
    cycle_latencies: list[float] = []

    sent_total = 0
    failure_total = 0
    attempts_total = 0
    pending_latest: int | None = None

    for timestamp, payload in records:
        event = str(payload.get("event"))
        if event == "cycle.start" and timestamp is not None:
            cycle_starts.append(timestamp)
        elif event == "cycle.complete" and timestamp is not None and cycle_starts:
            start = cycle_starts.pop(0)
            cycle_latencies.append(max((timestamp - start).total_seconds(), 0.0))
        elif event == "notification.sent":
            sent_total += 1
        elif event == "notification.final_failure":
            failure_total += 1
        elif event == "cycle.cost.metrics":
            attempts_total += int(payload.get("notification_attempts", 0))
            if "pending_total" in payload:
                pending_latest = int(payload["pending_total"])

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
        failed_reasons.append("pending_total missing from cycle.cost.metrics")
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
        f"- cycle_latency_p50_sec: `{report['cycle_latency_p50_sec']}`",
        f"- cycle_latency_p95_sec: `{report['cycle_latency_p95_sec']}`",
        f"- cycle_latency_max_sec: `{report['cycle_latency_max_sec']}`",
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
