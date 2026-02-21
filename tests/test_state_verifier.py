from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

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


def test_verify_json_state_missing_file_is_error_when_strict(tmp_path: Path) -> None:
    summary, issues = verify_json_state(tmp_path / "missing.json", strict=True)

    assert summary.exists is False
    assert issues[0].severity == "error"
    assert issues[0].code == "file_missing"


def test_verify_json_state_returns_read_failed_for_directory_path(tmp_path: Path) -> None:
    state_dir = tmp_path / "state_dir"
    state_dir.mkdir()

    summary, issues = verify_json_state(state_dir, strict=True)

    assert summary.exists is True
    assert issues[0].code == "read_failed"


def test_verify_json_state_rejects_non_dict_root(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(["not-a-dict"]), encoding="utf-8")

    summary, issues = verify_json_state(state_file, strict=True)

    assert summary.exists is True
    assert summary.records == 0
    assert issues[0].code == "invalid_root_type"


def test_verify_json_state_rejects_non_dict_events_payload(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"version": 2, "events": []}), encoding="utf-8")

    summary, issues = verify_json_state(state_file, strict=True)

    assert summary.exists is True
    assert summary.records == 0
    assert issues[0].code == "invalid_events_type"


def test_verify_json_state_detects_legacy_boolean_schema(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({"legacy-event-1": True, "legacy-event-2": False}),
        encoding="utf-8",
    )

    summary, issues = verify_json_state(state_file, strict=False)

    assert summary.records == 2
    assert summary.sent == 1
    assert summary.pending == 1
    assert any(issue.code == "legacy_schema_detected" for issue in issues)


def test_verify_json_state_collects_record_level_issues(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    now = utc_now_iso()
    payload = {
        "version": 2,
        "events": {
            "": {
                "area_code": "L1090000",
                "message": "empty id record",
                "report_url": None,
                "sent": False,
                "first_seen_at": now,
                "updated_at": now,
                "last_sent_at": None,
            },
            "bad-record-type": "not-a-dict",
            "bad-first-seen": {
                "area_code": "L1090000",
                "message": "bad first_seen_at",
                "report_url": None,
                "sent": False,
                "first_seen_at": "not-iso",
                "updated_at": now,
                "last_sent_at": None,
            },
            "bad-updated-at": {
                "area_code": "L1090000",
                "message": "bad updated_at",
                "report_url": None,
                "sent": False,
                "first_seen_at": now,
                "updated_at": "not-iso",
                "last_sent_at": None,
            },
            "bad-last-sent": {
                "area_code": "L1090000",
                "message": "bad last_sent_at",
                "report_url": None,
                "sent": True,
                "first_seen_at": now,
                "updated_at": now,
                "last_sent_at": "not-iso",
            },
        },
    }
    state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    summary, issues = verify_json_state(state_file, strict=True)
    issue_codes = [issue.code for issue in issues]

    assert summary.records == 5
    assert summary.sent == 1
    assert summary.pending == 2
    assert issue_codes.count("empty_event_id") == 1
    assert issue_codes.count("invalid_record_type") == 1
    assert issue_codes.count("invalid_timestamp") == 3


def test_verify_sqlite_state_missing_file_is_error_when_strict(tmp_path: Path) -> None:
    summary, issues = verify_sqlite_state(tmp_path / "missing.db", strict=True)

    assert summary.exists is False
    assert issues[0].severity == "error"
    assert issues[0].code == "file_missing"


def test_verify_sqlite_state_handles_open_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_state_file = tmp_path / "state.db"
    sqlite_state_file.write_text("placeholder", encoding="utf-8")

    def _raise_sqlite_error(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise sqlite3.Error("cannot open")

    monkeypatch.setattr("app.repositories.state_verifier.sqlite3.connect", _raise_sqlite_error)

    summary, issues = verify_sqlite_state(sqlite_state_file, strict=True)

    assert summary.exists is True
    assert issues[0].code == "open_failed"


def test_verify_sqlite_state_closes_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_state_file = tmp_path / "state.db"
    with sqlite3.connect(sqlite_state_file) as conn:
        conn.execute(
            """
            CREATE TABLE notifications (
              event_id TEXT PRIMARY KEY,
              area_code TEXT NOT NULL,
              message TEXT NOT NULL,
              report_url TEXT,
              sent INTEGER NOT NULL DEFAULT 0,
              first_seen_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              last_sent_at TEXT
            )
            """
        )

    original_connect = sqlite3.connect
    tracking: dict[str, bool] = {"closed": False}

    class _TrackingConnection:
        def __init__(self, conn: sqlite3.Connection) -> None:
            object.__setattr__(self, "_conn", conn)

        def __setattr__(self, name: str, value: object) -> None:
            if name == "_conn":
                object.__setattr__(self, name, value)
                return
            setattr(self._conn, name, value)

        def __getattr__(self, name: str):
            return getattr(self._conn, name)

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self._conn.__exit__(exc_type, exc, tb)

        def close(self) -> None:
            tracking["closed"] = True
            self._conn.close()

    def _tracking_connect(*args: object, **kwargs: object):
        return _TrackingConnection(original_connect(*args, **kwargs))

    monkeypatch.setattr("app.repositories.state_verifier.sqlite3.connect", _tracking_connect)
    summary, issues = verify_sqlite_state(sqlite_state_file, strict=True)

    assert summary.exists is True
    assert issues == []
    assert tracking["closed"] is True


def test_verify_sqlite_state_fails_when_notifications_table_missing(tmp_path: Path) -> None:
    sqlite_state_file = tmp_path / "state.db"
    with sqlite3.connect(sqlite_state_file):
        pass

    summary, issues = verify_sqlite_state(sqlite_state_file, strict=True)

    assert summary.exists is True
    assert any(issue.code == "missing_table" for issue in issues)


def test_verify_sqlite_state_detects_missing_columns(tmp_path: Path) -> None:
    sqlite_state_file = tmp_path / "state.db"
    with sqlite3.connect(sqlite_state_file) as conn:
        conn.execute(
            """
            CREATE TABLE notifications (
              event_id TEXT PRIMARY KEY,
              area_code TEXT NOT NULL
            )
            """
        )

    summary, issues = verify_sqlite_state(sqlite_state_file, strict=True)

    assert summary.exists is True
    assert any(issue.code == "missing_columns" for issue in issues)


def test_verify_sqlite_state_collects_field_and_timestamp_issues(tmp_path: Path) -> None:
    sqlite_state_file = tmp_path / "state.db"
    now = utc_now_iso()
    with sqlite3.connect(sqlite_state_file) as conn:
        conn.execute(
            """
            CREATE TABLE notifications (
              event_id TEXT,
              area_code TEXT,
              message TEXT,
              report_url TEXT,
              sent INTEGER,
              first_seen_at TEXT,
              updated_at TEXT,
              last_sent_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO notifications (
              event_id, area_code, message, report_url, sent,
              first_seen_at, updated_at, last_sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("event-invalid-sent", "L1090000", "m", None, 2, now, now, None),
                ("", "", "", None, 0, now, now, None),
                ("event-bad-first", "L1090000", "m", None, 0, "bad", now, None),
                ("event-bad-updated", "L1090000", "m", None, 0, now, "bad", None),
                ("event-bad-last", "L1090000", "m", None, 0, now, now, "bad"),
            ],
        )

    summary, issues = verify_sqlite_state(sqlite_state_file, strict=True)
    issue_by_code = {issue.code: issue.detail for issue in issues}

    assert summary.exists is True
    assert summary.records == 5
    assert issue_by_code["invalid_sent_value"] == "1"
    assert issue_by_code["invalid_required_field"] == "1"
    assert issue_by_code["invalid_timestamp"] == "3"


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


def test_verify_state_files_warning_only_passes_when_not_strict(tmp_path: Path) -> None:
    report = verify_state_files(
        json_state_file=tmp_path / "missing.json",
        sqlite_state_file=tmp_path / "missing.db",
        strict=False,
    )

    assert report.passed is True
    assert report.error_count == 0
    assert report.warning_count == 2
    assert {issue.code for issue in report.issues} == {"file_missing"}


def test_verify_state_files_missing_files_fail_when_strict(tmp_path: Path) -> None:
    report = verify_state_files(
        json_state_file=tmp_path / "missing.json",
        sqlite_state_file=tmp_path / "missing.db",
        strict=True,
    )

    assert report.passed is False
    assert report.error_count == 2
    assert report.warning_count == 0
    assert {issue.code for issue in report.issues} == {"file_missing"}
