from __future__ import annotations

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path


def _read_report(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_baseline(report_paths: list[Path]) -> dict[str, object]:
    if not report_paths:
        raise ValueError("at least one report path is required")

    metric_values: dict[str, list[float]] = {}
    metric_units: dict[str, str] = {}
    metric_better: dict[str, str] = {}

    for path in report_paths:
        report = _read_report(path)
        metrics: dict[str, dict[str, object]] = report["metrics"]  # type: ignore[assignment]
        for name, metric in metrics.items():
            value = float(metric["value"])
            metric_values.setdefault(name, []).append(value)
            metric_units[name] = str(metric["unit"])
            metric_better[name] = str(metric["better"])

    aggregated_metrics: dict[str, dict[str, object]] = {}
    for metric_name in sorted(metric_values):
        values = metric_values[metric_name]
        aggregated_metrics[metric_name] = {
            "value": round(float(statistics.median(values)), 3),
            "unit": metric_units[metric_name],
            "better": metric_better[metric_name],
            "samples": [round(value, 3) for value in values],
        }

    return {
        "meta": {
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "source_reports": [str(path) for path in report_paths],
            "source_count": len(report_paths),
        },
        "metrics": aggregated_metrics,
    }


def render_markdown(baseline: dict[str, object]) -> str:
    meta = baseline["meta"]
    metrics: dict[str, dict[str, object]] = baseline["metrics"]  # type: ignore[assignment]
    lines = [
        "## Performance Baseline (Median)",
        "",
        f"- created_at_utc: `{meta['created_at_utc']}`",
        f"- source_count: `{meta['source_count']}`",
        f"- source_reports: `{meta['source_reports']}`",
        "",
        "| metric | baseline | unit | better | samples |",
        "|---|---:|---|---|---|",
    ]
    for name in sorted(metrics):
        metric = metrics[name]
        lines.append(
            f"| `{name}` | {metric['value']} | {metric['unit']} | {metric['better']} | "
            f"`{metric['samples']}` |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build median baseline from perf reports.")
    parser.add_argument(
        "--reports",
        type=Path,
        nargs="+",
        required=True,
        help="Input perf report JSON paths.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Baseline JSON output path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    baseline = build_baseline(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    markdown = render_markdown(baseline)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(f"perf baseline written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
