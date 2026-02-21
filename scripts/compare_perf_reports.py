from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_report(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _status(*, better: str, delta: float) -> str:
    if abs(delta) < 1e-9:
        return "unchanged"
    if better == "lower":
        return "improved" if delta < 0 else "regressed"
    return "improved" if delta > 0 else "regressed"


def compare_reports(
    *,
    base_report: dict[str, object],
    head_report: dict[str, object],
) -> dict[str, object]:
    base_metrics: dict[str, dict[str, object]] = base_report["metrics"]  # type: ignore[assignment]
    head_metrics: dict[str, dict[str, object]] = head_report["metrics"]  # type: ignore[assignment]

    rows: list[dict[str, object]] = []
    for metric_name in sorted(set(base_metrics) & set(head_metrics)):
        base_metric = base_metrics[metric_name]
        head_metric = head_metrics[metric_name]
        base_value = float(base_metric["value"])
        head_value = float(head_metric["value"])
        unit = str(head_metric["unit"])
        better = str(head_metric["better"])
        delta = round(head_value - base_value, 3)
        pct = None if base_value == 0 else round((delta / base_value) * 100.0, 3)
        rows.append(
            {
                "metric": metric_name,
                "unit": unit,
                "better": better,
                "base": base_value,
                "head": head_value,
                "delta": delta,
                "delta_pct": pct,
                "status": _status(better=better, delta=delta),
            }
        )

    summary = {
        "improved": sum(1 for row in rows if row["status"] == "improved"),
        "regressed": sum(1 for row in rows if row["status"] == "regressed"),
        "unchanged": sum(1 for row in rows if row["status"] == "unchanged"),
    }
    return {
        "base_meta": base_report.get("meta", {}),
        "head_meta": head_report.get("meta", {}),
        "summary": summary,
        "rows": rows,
    }


def evaluate_regression_gate(
    *,
    compare_result: dict[str, object],
    max_regression_pct: float,
    allow_regression_metrics: set[str] | None = None,
) -> dict[str, object]:
    allow_metrics = allow_regression_metrics or set()
    rows: list[dict[str, object]] = compare_result["rows"]  # type: ignore[assignment]

    violations: list[dict[str, object]] = []
    ignored: list[dict[str, object]] = []
    for row in rows:
        if row.get("status") != "regressed":
            continue

        metric = str(row["metric"])
        delta_pct = row.get("delta_pct")
        if metric in allow_metrics:
            ignored.append(
                {
                    "metric": metric,
                    "delta_pct": delta_pct,
                    "reason": "allow_regression_metric",
                }
            )
            continue

        if delta_pct is None:
            violations.append(
                {
                    "metric": metric,
                    "delta_pct": None,
                    "reason": "delta_pct_unavailable_base_zero",
                }
            )
            continue

        regression_pct = abs(float(delta_pct))
        if regression_pct > max_regression_pct:
            violations.append(
                {
                    "metric": metric,
                    "delta_pct": round(float(delta_pct), 3),
                    "regression_pct": round(regression_pct, 3),
                    "max_regression_pct": round(max_regression_pct, 3),
                    "reason": "regression_pct_exceeded",
                }
            )

    return {
        "passed": not violations,
        "max_regression_pct": round(max_regression_pct, 3),
        "allow_regression_metrics": sorted(allow_metrics),
        "violations": violations,
        "ignored": ignored,
    }


def render_markdown(compare_result: dict[str, object]) -> str:
    summary: dict[str, int] = compare_result["summary"]  # type: ignore[assignment]
    rows: list[dict[str, object]] = compare_result["rows"]  # type: ignore[assignment]
    lines = [
        "## Performance Comparison (base -> head)",
        "",
        (
            f"- improved: `{summary['improved']}`"
            f" / regressed: `{summary['regressed']}`"
            f" / unchanged: `{summary['unchanged']}`"
        ),
    ]

    gate: dict[str, object] | None = compare_result.get("regression_gate")  # type: ignore[assignment]
    if isinstance(gate, dict):
        lines.extend(
            [
                (
                    f"- regression_gate: "
                    f"`{'PASS' if gate.get('passed') else 'FAIL'}`"
                    f" (max_regression_pct={gate.get('max_regression_pct')}%)"
                ),
                f"- allow_regression_metrics: `{gate.get('allow_regression_metrics')}`",
                f"- regression_violations: `{gate.get('violations')}`",
                f"- regression_ignored: `{gate.get('ignored')}`",
            ]
        )

    lines.extend(
        [
            "",
            "| metric | base | head | delta | delta % | better | status |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in rows:
        delta_pct = "-" if row["delta_pct"] is None else f"{row['delta_pct']}%"
        lines.append(
            f"| `{row['metric']}` | {row['base']} | {row['head']} | {row['delta']} | "
            f"{delta_pct} | {row['better']} | {row['status']} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two perf report JSON files.")
    parser.add_argument("--base", type=Path, required=True, help="Base report path.")
    parser.add_argument("--head", type=Path, required=True, help="Head report path.")
    parser.add_argument("--output", type=Path, required=True, help="Comparison JSON output path.")
    parser.add_argument(
        "--max-regression-pct",
        type=float,
        default=20.0,
        help="Maximum allowed regression percentage before failing the gate.",
    )
    parser.add_argument(
        "--allow-regression-metric",
        action="append",
        default=[],
        help="Metric name that is temporarily allowed to regress.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with code 1 when regression gate fails.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    base_report = _read_report(args.base)
    head_report = _read_report(args.head)
    compare_result = compare_reports(base_report=base_report, head_report=head_report)
    compare_result["regression_gate"] = evaluate_regression_gate(
        compare_result=compare_result,
        max_regression_pct=args.max_regression_pct,
        allow_regression_metrics=set(args.allow_regression_metric),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(compare_result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown = render_markdown(compare_result)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(f"perf comparison written: {args.output}")
    gate: dict[str, object] = compare_result["regression_gate"]  # type: ignore[assignment]
    if args.fail_on_regression and not bool(gate["passed"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
