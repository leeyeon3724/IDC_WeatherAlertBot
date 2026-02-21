from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.domain.models import AlertNotification
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_models import utc_now_iso
from app.repositories.state_verifier import (
    verify_json_state,
    verify_sqlite_state,
    verify_state_files,
)


def test_verify_json_state_missing_file_is_warning_when_not_strict(tmp_path: Path) -> None:
    summary, issues = verify_json_state(tmp_path / "missing.json", strict=False)

    assert summary.exists is False
    assert issues[0].severity == "warning"
    assert issues[0].code == "file_missing"


def test_verify_sqlite_state_fails_when_notifications_table_missing(tmp_path: Path) -> None:
    sqlite_state_file = tmp_path / "state.db"
    with sqlite3.connect(sqlite_state_file):
        pass

    summary, issues = verify_sqlite_state(sqlite_state_file, strict=True)

    assert summary.exists is True
    assert any(issue.code == "missing_table" for issue in issues)


def test_verify_state_files_passes_for_valid_json_and_sqlite(tmp_path: Path) -> None:
    json_state_file = tmp_path / "state.json"
    sqlite_state_file = tmp_path / "state.db"
    now = utc_now_iso()

    json_state_file.write_text(
        json.dumps(
            {
                "version": 2,
                "events": {
                    "event-1": {
                        "area_code": "L1090000",
                        "message": "m",
                        "report_url": None,
                        "sent": False,
                        "first_seen_at": now,
                        "updated_at": now,
                        "last_sent_at": None,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sqlite_repo = SqliteStateRepository(sqlite_state_file)
    sqlite_repo.upsert_notifications(
        [
            AlertNotification(
                event_id="event-1",
                area_code="L1090000",
                message="m",
                report_url=None,
            )
        ]
    )

    report = verify_state_files(
        json_state_file=json_state_file,
        sqlite_state_file=sqlite_state_file,
        strict=True,
    )

    assert report.passed is True
    assert report.error_count == 0
