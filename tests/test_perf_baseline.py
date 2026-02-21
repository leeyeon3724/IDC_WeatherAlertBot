from __future__ import annotations

import json
from pathlib import Path

from scripts.perf_baseline import build_baseline, render_markdown


def _write_report(path: Path, *, created_at: str, metric_value: float) -> None:
    payload = {
        "meta": {
            "created_at_utc": created_at,
        },
        "metrics": {
            "sqlite.upsert.duration_ms": {
                "value": metric_value,
                "unit": "ms",
                "better": "lower",
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_baseline_applies_max_samples_in_time_order(tmp_path: Path) -> None:
    report_a = tmp_path / "a.json"
    report_b = tmp_path / "b.json"
    report_c = tmp_path / "c.json"
    _write_report(report_a, created_at="2026-02-21T00:00:01+00:00", metric_value=10.0)
    _write_report(report_b, created_at="2026-02-21T00:00:02+00:00", metric_value=20.0)
    _write_report(report_c, created_at="2026-02-21T00:00:03+00:00", metric_value=30.0)

    baseline = build_baseline([report_c, report_a, report_b], max_samples=2)
    metric = baseline["metrics"]["sqlite.upsert.duration_ms"]  # type: ignore[index]

    assert baseline["meta"]["retained_count"] == 2  # type: ignore[index]
    assert baseline["meta"]["max_samples"] == 2  # type: ignore[index]
    assert metric["samples"] == [20.0, 30.0]  # type: ignore[index]
    assert metric["value"] == 25.0  # type: ignore[index]


def test_render_markdown_includes_trend_column(tmp_path: Path) -> None:
    report_a = tmp_path / "a.json"
    report_b = tmp_path / "b.json"
    _write_report(report_a, created_at="2026-02-21T00:00:01+00:00", metric_value=10.0)
    _write_report(report_b, created_at="2026-02-21T00:00:02+00:00", metric_value=20.0)

    baseline = build_baseline([report_a, report_b], max_samples=20)
    markdown = render_markdown(baseline)

    assert "| metric | baseline | unit | better | trend | samples |" in markdown
    assert "`.#`" in markdown
