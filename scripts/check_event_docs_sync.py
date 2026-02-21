from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RE_EVENT_ASSIGN = re.compile(r'^\s*[A-Z0-9_]+\s*=\s*"([^"]+)"\s*$')
RE_EVENT_SCHEMA_VERSION = re.compile(r"^\s*EVENT_SCHEMA_VERSION\s*=\s*([0-9]+)\s*$")
RE_EVENTS_DOC_LINE = re.compile(r"^\s*-\s+`([^`]+)`\s*:")
RE_EVENTS_DOC_SCHEMA_VERSION = re.compile(r"^\s*-\s+schema_version:\s*`?([0-9]+)`?\s*$")
RE_EVENTS_DOC_CHANGELOG_ROW = re.compile(r"^\|\s*([0-9]+)\s*\|")
RE_OPERATION_TABLE_EVENT = re.compile(r"^\|\s*`([^`]+)`")

OPERATION_REQUIRED_EVENTS = {
    "cycle.cost.metrics",
    "area.failed",
    "notification.final_failure",
    "health.notification.sent",
    "state.cleanup.failed",
    "state.migration.failed",
}


def parse_events_py(path: Path) -> set[str]:
    events: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RE_EVENT_ASSIGN.match(line)
        if match:
            events.add(match.group(1).strip())
    return events


def parse_event_schema_version(path: Path) -> int | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RE_EVENT_SCHEMA_VERSION.match(line)
        if match:
            return int(match.group(1))
    return None


def parse_events_doc(path: Path) -> set[str]:
    events: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RE_EVENTS_DOC_LINE.match(line)
        if match:
            events.add(match.group(1).strip())
    return events


def parse_events_doc_schema_version(path: Path) -> int | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RE_EVENTS_DOC_SCHEMA_VERSION.match(line)
        if match:
            return int(match.group(1))
    return None


def parse_events_doc_changelog_versions(path: Path) -> set[int]:
    versions: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RE_EVENTS_DOC_CHANGELOG_ROW.match(line)
        if match:
            versions.add(int(match.group(1)))
    return versions


def parse_operation_alarm_events(path: Path) -> set[str]:
    events: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RE_OPERATION_TABLE_EVENT.match(line)
        if match:
            events.add(match.group(1).strip())
    return events


def build_report(
    *,
    events_py_path: Path,
    events_doc_path: Path,
    operation_doc_path: Path,
) -> dict[str, object]:
    code_events = parse_events_py(events_py_path)
    event_schema_version = parse_event_schema_version(events_py_path)
    events_doc_events = parse_events_doc(events_doc_path)
    events_doc_schema_version = parse_events_doc_schema_version(events_doc_path)
    events_doc_changelog_versions = sorted(parse_events_doc_changelog_versions(events_doc_path))
    operation_events = parse_operation_alarm_events(operation_doc_path)

    missing_in_events_doc = sorted(code_events - events_doc_events)
    unknown_in_events_doc = sorted(events_doc_events - code_events)
    missing_in_operation = sorted(OPERATION_REQUIRED_EVENTS - operation_events)
    unknown_in_operation = sorted(operation_events - code_events)
    schema_version_match = (
        event_schema_version is not None
        and events_doc_schema_version is not None
        and event_schema_version == events_doc_schema_version
    )
    schema_version_in_changelog = (
        event_schema_version is not None and event_schema_version in events_doc_changelog_versions
    )

    passed = not (
        missing_in_events_doc
        or unknown_in_events_doc
        or missing_in_operation
        or unknown_in_operation
        or not schema_version_match
        or not schema_version_in_changelog
    )
    return {
        "passed": passed,
        "events_py_count": len(code_events),
        "events_doc_count": len(events_doc_events),
        "events_schema_version": event_schema_version,
        "events_doc_schema_version": events_doc_schema_version,
        "events_doc_changelog_versions": events_doc_changelog_versions,
        "schema_version_match": schema_version_match,
        "schema_version_in_changelog": schema_version_in_changelog,
        "operation_alarm_event_count": len(operation_events),
        "missing_in_events_doc": missing_in_events_doc,
        "unknown_in_events_doc": unknown_in_events_doc,
        "missing_in_operation": missing_in_operation,
        "unknown_in_operation": unknown_in_operation,
    }


def render_markdown(report: dict[str, object]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Event Docs Consistency",
        "",
        f"- status: `{status}`",
        f"- events.py count: `{report['events_py_count']}`",
        f"- docs/EVENTS.md count: `{report['events_doc_count']}`",
        f"- events.py schema_version: `{report['events_schema_version']}`",
        f"- docs/EVENTS.md schema_version: `{report['events_doc_schema_version']}`",
        f"- schema_version_match: `{report['schema_version_match']}`",
        f"- schema_version_in_changelog: `{report['schema_version_in_changelog']}`",
        f"- docs/OPERATION.md alarm-event count: `{report['operation_alarm_event_count']}`",
        "",
        f"- missing_in_events_doc: `{report['missing_in_events_doc']}`",
        f"- unknown_in_events_doc: `{report['unknown_in_events_doc']}`",
        f"- missing_in_operation: `{report['missing_in_operation']}`",
        f"- unknown_in_operation: `{report['unknown_in_operation']}`",
        f"- events_doc_changelog_versions: `{report['events_doc_changelog_versions']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate events docs consistency.")
    parser.add_argument(
        "--events-py",
        type=Path,
        default=Path("app/observability/events.py"),
        help="Path to events.py",
    )
    parser.add_argument(
        "--events-doc",
        type=Path,
        default=Path("docs/EVENTS.md"),
        help="Path to EVENTS.md",
    )
    parser.add_argument(
        "--operation-doc",
        type=Path,
        default=Path("docs/OPERATION.md"),
        help="Path to OPERATION.md",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    report = build_report(
        events_py_path=args.events_py,
        events_doc_path=args.events_doc,
        operation_doc_path=args.operation_doc,
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
