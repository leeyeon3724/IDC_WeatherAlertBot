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


def test_build_report_includes_perf_script_tests_for_scripts_change() -> None:
    report = build_report(["scripts/compare_perf_reports.py"])

    assert report["mode"] == "fast"
    selected = set(report["selected_tests"])
    assert "tests/test_compare_perf_reports.py" in selected
    assert "tests/test_perf_baseline.py" in selected
    assert "tests/test_alarm_rules_sync.py" in selected


def test_build_report_returns_docs_subset_when_changed_files_empty() -> None:
    report = build_report([])

    assert report["mode"] == "fast"
    assert set(report["selected_tests"]) == {
        "tests/test_repo_hygiene.py",
        "tests/test_event_docs_sync.py",
        "tests/test_contract_snapshots.py",
    }


def test_build_report_falls_back_to_full_for_unknown_change_mapping() -> None:
    report = build_report(["app/unknown_module.py"])

    assert report["mode"] == "full"
    assert report["selected_tests"] == []
    assert report["reasons"] == ["could not map changed files to safe fast-test subset"]


def test_build_report_includes_changed_test_file_directly() -> None:
    report = build_report(["tests/test_domain.py"])

    assert report["mode"] == "fast"
    assert "tests/test_domain.py" in set(report["selected_tests"])
