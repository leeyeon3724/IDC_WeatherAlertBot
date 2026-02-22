from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RE_CHECKBOX = re.compile(r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<label>.+?)\s*$")

QUALITY_CHECK_LABELS = [
    "`python3 -m ruff check .`",
    "`python3 -m mypy`",
    "`python3 -m scripts.check_architecture_rules`",
    "`python3 -m scripts.check_event_docs_sync`",
    "`python3 -m scripts.check_alarm_rules_sync`",
    "`python3 -m scripts.check_repo_hygiene`",
    "`python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc`",
]

EVENT_IMPACT_LABELS = [
    "`docs/EVENTS.md` 이벤트/필드 사전 반영",
    "`docs/OPERATION.md` 알람-대응 매핑 영향 검토",
    "대시보드/알람 룰 영향도 검토",
    "`scripts.check_event_docs_sync` 통과 확인",
]

DOORAY_IMPACT_LABELS = [
    "`docs/DOORAY_WEBHOOK_REFERENCE.md` 프로젝트 적용 상태 반영",
    "`tests/services/test_notifier.py` 정책 회귀 테스트/수정 반영",
]


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_changed_files(path: Path) -> list[str]:
    return [line.strip() for line in _read_text(path).splitlines() if line.strip()]


def _is_checked(body: str, label_fragment: str) -> bool:
    for line in body.splitlines():
        match = RE_CHECKBOX.match(line)
        if not match:
            continue
        if label_fragment not in match.group("label"):
            continue
        return match.group("mark").lower() == "x"
    return False


def _requires_event_impact(changed_files: list[str]) -> bool:
    for file_name in changed_files:
        if file_name.startswith("app/observability/"):
            return True
        if file_name in {"docs/EVENTS.md", "docs/OPERATION.md"}:
            return True
    return False


def _requires_dooray_impact(changed_files: list[str]) -> bool:
    for file_name in changed_files:
        if file_name == "app/services/notifier.py":
            return True
        if file_name == "docs/DOORAY_WEBHOOK_REFERENCE.md":
            return True
    return False


def build_report(*, pr_body: str, changed_files: list[str]) -> dict[str, object]:
    missing_quality_checks = [
        label for label in QUALITY_CHECK_LABELS if not _is_checked(pr_body, label)
    ]

    event_impact_required = _requires_event_impact(changed_files)
    missing_event_checks: list[str] = []
    if event_impact_required:
        missing_event_checks = [
            label for label in EVENT_IMPACT_LABELS if not _is_checked(pr_body, label)
        ]

    dooray_impact_required = _requires_dooray_impact(changed_files)
    missing_dooray_checks: list[str] = []
    if dooray_impact_required:
        missing_dooray_checks = [
            label for label in DOORAY_IMPACT_LABELS if not _is_checked(pr_body, label)
        ]

    passed = not missing_quality_checks and not missing_event_checks and not missing_dooray_checks
    return {
        "passed": passed,
        "changed_files_count": len(changed_files),
        "event_impact_required": event_impact_required,
        "dooray_impact_required": dooray_impact_required,
        "missing_quality_checks": missing_quality_checks,
        "missing_event_checks": missing_event_checks,
        "missing_dooray_checks": missing_dooray_checks,
    }


def render_markdown(report: dict[str, object]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## PR Checklist Validation",
        "",
        f"- status: `{status}`",
        f"- changed_files_count: `{report['changed_files_count']}`",
        f"- event_impact_required: `{report['event_impact_required']}`",
        f"- dooray_impact_required: `{report['dooray_impact_required']}`",
        "",
        f"- missing_quality_checks: `{report['missing_quality_checks']}`",
        f"- missing_event_checks: `{report['missing_event_checks']}`",
        f"- missing_dooray_checks: `{report['missing_dooray_checks']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PR template checklist in CI.")
    parser.add_argument(
        "--pr-body-file",
        type=Path,
        required=True,
        help="Path to markdown file containing pull request body.",
    )
    parser.add_argument(
        "--changed-files-file",
        type=Path,
        required=True,
        help="Path to changed files list (one file path per line).",
    )
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output.",
    )
    args = parser.parse_args()

    report = build_report(
        pr_body=_read_text(args.pr_body_file),
        changed_files=_read_changed_files(args.changed_files_file),
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
