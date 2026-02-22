from __future__ import annotations

from scripts.compare_perf_reports import (
    compare_reports,
    evaluate_regression_gate,
    render_markdown,
)


def _report(value: float, *, better: str = "lower") -> dict[str, object]:
    return {
        "meta": {"created_at_utc": "2026-02-21T00:00:00+00:00"},
        "metrics": {
            "sqlite.upsert.duration_ms": {
                "value": value,
                "unit": "ms",
                "better": better,
            }
        },
    }


def test_regression_gate_fails_when_regression_pct_exceeds_threshold() -> None:
    result = compare_reports(base_report=_report(100.0), head_report=_report(130.0))
    gate = evaluate_regression_gate(
        compare_result=result,
        max_regression_pct=20.0,
    )

    assert gate["passed"] is False
    assert len(gate["violations"]) == 1
    assert gate["violations"][0]["metric"] == "sqlite.upsert.duration_ms"


def test_regression_gate_allows_metric_exception() -> None:
    result = compare_reports(base_report=_report(100.0), head_report=_report(130.0))
    gate = evaluate_regression_gate(
        compare_result=result,
        max_regression_pct=20.0,
        allow_regression_metrics={"sqlite.upsert.duration_ms"},
    )

    assert gate["passed"] is True
    assert gate["violations"] == []
    assert len(gate["ignored"]) == 1


def test_render_markdown_includes_regression_gate_summary() -> None:
    result = compare_reports(base_report=_report(100.0), head_report=_report(95.0))
    result["regression_gate"] = evaluate_regression_gate(
        compare_result=result,
        max_regression_pct=20.0,
    )

    markdown = render_markdown(result)

    assert "regression_gate" in markdown
    assert "Performance Comparison" in markdown


def test_regression_gate_fails_when_base_value_is_zero_and_metric_regresses() -> None:
    result = compare_reports(base_report=_report(0.0), head_report=_report(10.0))
    gate = evaluate_regression_gate(compare_result=result, max_regression_pct=20.0)

    assert gate["passed"] is False
    assert gate["violations"] == [
        {
            "metric": "sqlite.upsert.duration_ms",
            "delta_pct": None,
            "reason": "delta_pct_unavailable_base_zero",
        }
    ]


def test_compare_reports_treats_higher_better_metric_as_improved() -> None:
    result = compare_reports(
        base_report=_report(100.0, better="higher"),
        head_report=_report(130.0, better="higher"),
    )
    row = result["rows"][0]

    assert row["status"] == "improved"
    assert row["delta"] == 30.0
    assert row["delta_pct"] == 30.0
