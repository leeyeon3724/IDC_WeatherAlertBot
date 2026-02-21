from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.check_event_docs_sync import build_report


def _write(path: Path, content: str) -> None:
    normalized = textwrap.dedent(content).strip() + "\n"
    path.write_text(normalized, encoding="utf-8")


def _operation_doc_with_required_events() -> str:
    return """
    | Signal | Note |
    |---|---|
    | `area.failed` | fail |
    | `notification.final_failure` | fail |
    | `health.notification.sent` | health |
    | `state.cleanup.failed` | cleanup |
    | `state.migration.failed` | migration |
    """


def test_build_report_passes_with_schema_version_and_changelog(tmp_path: Path) -> None:
    events_py = tmp_path / "events.py"
    events_doc = tmp_path / "EVENTS.md"
    operation_doc = tmp_path / "OPERATION.md"

    _write(
        events_py,
        """
        EVENT_SCHEMA_VERSION = 2
        AREA_FAILED = "area.failed"
        NOTIFICATION_FINAL_FAILURE = "notification.final_failure"
        HEALTH_NOTIFICATION_SENT = "health.notification.sent"
        STATE_CLEANUP_FAILED = "state.cleanup.failed"
        STATE_MIGRATION_FAILED = "state.migration.failed"
        """,
    )
    _write(
        events_doc,
        """
        - schema_version: `2`

        | version | date | change | compatibility |
        |---|---|---|---|
        | 1 | 2026-02-20 | init | initial |
        | 2 | 2026-02-21 | update | backward-compatible |

        - `area.failed`: fields
        - `notification.final_failure`: fields
        - `health.notification.sent`: fields
        - `state.cleanup.failed`: fields
        - `state.migration.failed`: fields
        """,
    )
    _write(operation_doc, _operation_doc_with_required_events())

    report = build_report(
        events_py_path=events_py,
        events_doc_path=events_doc,
        operation_doc_path=operation_doc,
    )

    assert report["passed"] is True
    assert report["schema_version_match"] is True
    assert report["schema_version_in_changelog"] is True
    assert report["events_schema_version"] == 2
    assert report["events_doc_schema_version"] == 2


def test_build_report_fails_when_schema_version_not_in_changelog(tmp_path: Path) -> None:
    events_py = tmp_path / "events.py"
    events_doc = tmp_path / "EVENTS.md"
    operation_doc = tmp_path / "OPERATION.md"

    _write(
        events_py,
        """
        EVENT_SCHEMA_VERSION = 3
        AREA_FAILED = "area.failed"
        NOTIFICATION_FINAL_FAILURE = "notification.final_failure"
        HEALTH_NOTIFICATION_SENT = "health.notification.sent"
        STATE_CLEANUP_FAILED = "state.cleanup.failed"
        STATE_MIGRATION_FAILED = "state.migration.failed"
        """,
    )
    _write(
        events_doc,
        """
        - schema_version: `3`

        | version | date | change | compatibility |
        |---|---|---|---|
        | 1 | 2026-02-20 | init | initial |
        | 2 | 2026-02-21 | update | backward-compatible |

        - `area.failed`: fields
        - `notification.final_failure`: fields
        - `health.notification.sent`: fields
        - `state.cleanup.failed`: fields
        - `state.migration.failed`: fields
        """,
    )
    _write(operation_doc, _operation_doc_with_required_events())

    report = build_report(
        events_py_path=events_py,
        events_doc_path=events_doc,
        operation_doc_path=operation_doc,
    )

    assert report["passed"] is False
    assert report["schema_version_match"] is True
    assert report["schema_version_in_changelog"] is False
