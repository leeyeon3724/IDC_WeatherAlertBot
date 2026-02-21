from __future__ import annotations

from scripts.update_testing_snapshot import parse_test_snapshot, update_testing_doc


def test_parse_test_snapshot_extracts_passed_and_coverage() -> None:
    pytest_output = """
    ......
    167 passed in 29.04s
    Required test coverage of 80.0% reached. Total coverage: 91.54%
    """

    passed_count, coverage_text = parse_test_snapshot(pytest_output)

    assert passed_count == 167
    assert coverage_text == "91.54%"


def test_parse_test_snapshot_falls_back_to_total_line_percent() -> None:
    pytest_output = """
    ......
    12 passed in 1.00s
    TOTAL                                  140      3     42      0    98%
    """

    passed_count, coverage_text = parse_test_snapshot(pytest_output)

    assert passed_count == 12
    assert coverage_text == "98%"


def test_update_testing_doc_replaces_snapshot_values_preserving_minimum() -> None:
    doc_text = """# TESTING

## 2) 현재 스냅샷

- 테스트 수: `1`
- 전체 커버리지: `2%`
- 최소 커버리지 기준: `85%`

## 3) 현재 기준
"""

    updated = update_testing_doc(doc_text, passed_count=167, coverage_text="91.54%")

    assert "- 테스트 수: `167`" in updated
    assert "- 전체 커버리지: `91.54%`" in updated
    assert "- 최소 커버리지 기준: `85%`" in updated


def test_update_testing_doc_defaults_minimum_coverage_if_missing() -> None:
    doc_text = """# TESTING

## 2) 현재 스냅샷

- 테스트 수: `1`
- 전체 커버리지: `2%`

## 3) 현재 기준
"""

    updated = update_testing_doc(doc_text, passed_count=10, coverage_text="80%")

    assert "- 테스트 수: `10`" in updated
    assert "- 전체 커버리지: `80%`" in updated
    assert "- 최소 커버리지 기준: `80%`" in updated
