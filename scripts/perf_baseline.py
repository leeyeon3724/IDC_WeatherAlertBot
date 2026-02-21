from __future__ import annotations

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path


def _read_report(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_created_at(report: dict[str, object], *, fallback_index: int) -> str:
    meta = report.get("meta")
    if isinstance(meta, dict):
        created_at = meta.get("created_at_utc")
        if isinstance(created_at, str) and created_at:
            return created_at
    # Preserve caller order when timestamp is unavailable.
    return f"order:{fallback_index:06d}"


def _trend_chart(values: list[float]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return "*"
    low = min(values)
    high = max(values)
    if high == low:
        return "=" * len(values)

    levels = "._-:=+*#"
    span = high - low
    chart = []
    for value in values:
        normalized = (value - low) / span
        index = round(normalized * (len(levels) - 1))
        chart.append(levels[index])
    return "".join(chart)


def build_baseline(report_paths: list[Path], *, max_samples: int = 20) -> dict[str, object]:
    if not report_paths:
        raise ValueError("at least one report path is required")
    if max_samples <= 0:
        raise ValueError("max_samples must be > 0")

    loaded_reports: list[tuple[str, int, Path, dict[str, object]]] = []
    for index, path in enumerate(report_paths):
        report = _read_report(path)
        created_at = _report_created_at(report, fallback_index=index)
        loaded_reports.append((created_at, index, path, report))

    loaded_reports.sort(key=lambda item: (item[0], item[1]))
    retained_reports = loaded_reports[-max_samples:]

    metric_values: dict[str, list[float]] = {}
    metric_units: dict[str, str] = {}
    metric_better: dict[str, str] = {}

    for _, _, _, report in retained_reports:
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
            "trend_chart": _trend_chart(values),
        }

    return {
        "meta": {
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "source_reports": [str(path) for path in report_paths],
            "source_count": len(report_paths),
            "retained_reports": [str(path) for _, _, path, _ in retained_reports],
            "retained_count": len(retained_reports),
            "max_samples": max_samples,
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
        f"- retained_count: `{meta['retained_count']}` / max_samples: `{meta['max_samples']}`",
        f"- source_reports: `{meta['source_reports']}`",
        f"- retained_reports: `{meta['retained_reports']}`",
        "",
        "| metric | baseline | unit | better | trend | samples |",
        "|---|---:|---|---|---|---|",
    ]
    for name in sorted(metrics):
        metric = metrics[name]
        lines.append(
            f"| `{name}` | {metric['value']} | {metric['unit']} | {metric['better']} | "
            f"`{metric['trend_chart']}` | `{metric['samples']}` |"
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
    parser.add_argument(
        "--max-samples",
        type=int,
        default=20,
        help="Maximum number of source report samples retained in baseline.",
    )
    args = parser.parse_args()

    if args.max_samples <= 0:
        parser.error("--max-samples must be > 0")

    baseline = build_baseline(args.reports, max_samples=args.max_samples)
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
