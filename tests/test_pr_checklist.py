from __future__ import annotations

from scripts.check_pr_checklist import build_report


def _body_with_all_checks() -> str:
    return """
    - [x] `python3 -m ruff check .`
    - [x] `python3 -m mypy`
    - [x] `python3 -m scripts.check_architecture_rules`
    - [x] `python3 -m scripts.check_event_docs_sync`
    - [x] `python3 -m scripts.check_alarm_rules_sync`
    - [x] `python3 -m scripts.check_repo_hygiene`
    - [x] `python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc`
    - [x] `docs/EVENTS.md` 이벤트/필드 사전 반영
    - [x] `docs/OPERATION.md` 알람-대응 매핑 영향 검토
    - [x] 대시보드/알람 룰 영향도 검토(필드명, 이벤트명, 임계값)
    - [x] `scripts.check_event_docs_sync` 통과 확인
    """


def test_build_report_passes_with_checked_items() -> None:
    report = build_report(
        pr_body=_body_with_all_checks(),
        changed_files=["app/observability/events.py", "docs/EVENTS.md"],
    )

    assert report["passed"] is True
    assert report["event_impact_required"] is True
    assert report["missing_quality_checks"] == []
    assert report["missing_event_checks"] == []


def test_build_report_fails_when_event_impact_required_but_unchecked() -> None:
    body = """
    - [x] `python3 -m ruff check .`
    - [x] `python3 -m mypy`
    - [x] `python3 -m scripts.check_architecture_rules`
    - [x] `python3 -m scripts.check_event_docs_sync`
    - [x] `python3 -m scripts.check_alarm_rules_sync`
    - [x] `python3 -m scripts.check_repo_hygiene`
    - [x] `python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc`
    - [ ] `docs/EVENTS.md` 이벤트/필드 사전 반영
    - [ ] `docs/OPERATION.md` 알람-대응 매핑 영향 검토
    - [ ] 대시보드/알람 룰 영향도 검토(필드명, 이벤트명, 임계값)
    - [ ] `scripts.check_event_docs_sync` 통과 확인
    """

    report = build_report(
        pr_body=body,
        changed_files=["app/observability/events.py"],
    )

    assert report["passed"] is False
    assert report["event_impact_required"] is True
    assert report["missing_quality_checks"] == []
    assert len(report["missing_event_checks"]) == 4


def test_build_report_fails_when_required_quality_checks_are_missing() -> None:
    body = """
    - [x] `python3 -m ruff check .`
    - [ ] `python3 -m mypy`
    - [x] `python3 -m scripts.check_architecture_rules`
    - [ ] `python3 -m scripts.check_event_docs_sync`
    - [x] `python3 -m scripts.check_alarm_rules_sync`
    - [ ] `python3 -m scripts.check_repo_hygiene`
    - [x] `python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc`
    """

    report = build_report(
        pr_body=body,
        changed_files=["app/services/notifier.py"],
    )

    assert report["passed"] is False
    assert report["event_impact_required"] is False
    assert report["missing_event_checks"] == []
    assert report["missing_quality_checks"] == [
        "`python3 -m mypy`",
        "`python3 -m scripts.check_event_docs_sync`",
        "`python3 -m scripts.check_repo_hygiene`",
    ]
