from __future__ import annotations

from scripts.select_tests import build_report


def test_build_report_selects_fast_subset_for_service_change() -> None:
    report = build_report(["app/services/notifier.py"])

    assert report["mode"] == "fast"
    selected = set(report["selected_tests"])
    assert "tests/test_notifier.py" in selected
    assert "tests/test_process_cycle.py" in selected


def test_build_report_returns_full_for_ci_workflow_change() -> None:
    report = build_report([".github/workflows/ci.yml"])

    assert report["mode"] == "full"
    assert report["selected_tests"] == []


def test_build_report_uses_docs_subset_for_docs_only_change() -> None:
    report = build_report(["docs/OPERATION.md", "README.md"])

    assert report["mode"] == "fast"
    selected = set(report["selected_tests"])
    assert "tests/test_repo_hygiene.py" in selected
    assert "tests/test_event_docs_sync.py" in selected
