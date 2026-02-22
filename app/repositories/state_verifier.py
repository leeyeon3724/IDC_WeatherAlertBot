from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.repositories.state_models import parse_iso_to_utc

REQUIRED_SQLITE_COLUMNS = {
    "event_id",
    "area_code",
    "message",
    "report_url",
    "sent",
    "first_seen_at",
    "updated_at",
    "last_sent_at",
}


@dataclass(frozen=True)
class VerificationIssue:
    repository: str
    severity: str
    code: str
    detail: str


@dataclass(frozen=True)
class RepositoryVerificationSummary:
    repository: str
    file_path: str
    exists: bool
    records: int
    sent: int
    pending: int


@dataclass(frozen=True)
class StateVerificationReport:
    summaries: list[RepositoryVerificationSummary]
    issues: list[VerificationIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def passed(self) -> bool:
        return self.error_count == 0


def _issue(repository: str, severity: str, code: str, detail: str) -> VerificationIssue:
    return VerificationIssue(
        repository=repository,
        severity=severity,
        code=code,
        detail=detail,
    )


def _summary(
    *,
    repository: str,
    file_path: Path,
    exists: bool,
    records: int = 0,
    sent: int = 0,
    pending: int = 0,
) -> RepositoryVerificationSummary:
    return RepositoryVerificationSummary(
        repository=repository,
        file_path=str(file_path),
        exists=exists,
        records=records,
        sent=sent,
        pending=pending,
    )


def _failure_result(
    *,
    repository: str,
    file_path: Path,
    issues: list[VerificationIssue],
    severity: str,
    code: str,
    detail: str,
    exists: bool,
) -> tuple[RepositoryVerificationSummary, list[VerificationIssue]]:
    issues.append(_issue(repository, severity, code, detail))
    return _summary(repository=repository, file_path=file_path, exists=exists), issues


def _missing_file_result(
    *,
    repository: str,
    file_path: Path,
    strict: bool,
    issues: list[VerificationIssue],
) -> tuple[RepositoryVerificationSummary, list[VerificationIssue]]:
    severity = "error" if strict else "warning"
    return _failure_result(
        repository=repository,
        file_path=file_path,
        issues=issues,
        severity=severity,
        code="file_missing",
        detail=str(file_path),
        exists=False,
    )


def verify_json_state(file_path: Path, *, strict: bool = False) -> tuple[
    RepositoryVerificationSummary,
    list[VerificationIssue],
]:
    issues: list[VerificationIssue] = []
    repository = "json"
    path = Path(file_path)

    if not path.exists():
        return _missing_file_result(
            repository=repository,
            file_path=path,
            strict=strict,
            issues=issues,
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _failure_result(
            repository=repository,
            file_path=path,
            issues=issues,
            severity="error",
            code="invalid_json",
            detail=str(exc),
            exists=True,
        )
    except OSError as exc:
        return _failure_result(
            repository=repository,
            file_path=path,
            issues=issues,
            severity="error",
            code="read_failed",
            detail=str(exc),
            exists=True,
        )

    if not isinstance(raw, dict):
        return _failure_result(
            repository=repository,
            file_path=path,
            issues=issues,
            severity="error",
            code="invalid_root_type",
            detail=type(raw).__name__,
            exists=True,
        )

    records_obj: Any = raw.get("events", raw)
    if not isinstance(records_obj, dict):
        return _failure_result(
            repository=repository,
            file_path=path,
            issues=issues,
            severity="error",
            code="invalid_events_type",
            detail=type(records_obj).__name__,
            exists=True,
        )

    if records_obj and all(isinstance(value, (bool, int)) for value in records_obj.values()):
        sent = sum(1 for value in records_obj.values() if bool(value))
        pending = len(records_obj) - sent
        issues.append(_issue(repository, "warning", "legacy_schema_detected", "boolean map"))
        return (
            _summary(
                repository=repository,
                file_path=path,
                exists=True,
                records=len(records_obj),
                sent=sent,
                pending=pending,
            ),
            issues,
        )

    sent = 0
    pending = 0
    for event_id, record in records_obj.items():
        if not str(event_id).strip():
            issues.append(_issue(repository, "error", "empty_event_id", repr(event_id)))
            continue
        if not isinstance(record, dict):
            issues.append(
                _issue(
                    repository,
                    "error",
                    "invalid_record_type",
                    f"event_id={event_id} type={type(record).__name__}",
                )
            )
            continue

        sent_flag = bool(record.get("sent", False))
        if sent_flag:
            sent += 1
        else:
            pending += 1

        for key in ("first_seen_at", "updated_at"):
            if parse_iso_to_utc(record.get(key)) is None:
                issues.append(
                    _issue(
                        repository,
                        "error",
                        "invalid_timestamp",
                        f"event_id={event_id} key={key}",
                    )
                )
        last_sent_at = record.get("last_sent_at")
        if last_sent_at is not None and parse_iso_to_utc(last_sent_at) is None:
            issues.append(
                _issue(
                    repository,
                    "error",
                    "invalid_timestamp",
                    f"event_id={event_id} key=last_sent_at",
                )
            )

    return (
        _summary(
            repository=repository,
            file_path=path,
            exists=True,
            records=len(records_obj),
            sent=sent,
            pending=pending,
        ),
        issues,
    )


def verify_sqlite_state(file_path: Path, *, strict: bool = False) -> tuple[
    RepositoryVerificationSummary,
    list[VerificationIssue],
]:
    issues: list[VerificationIssue] = []
    repository = "sqlite"
    path = Path(file_path)

    if not path.exists():
        return _missing_file_result(
            repository=repository,
            file_path=path,
            strict=strict,
            issues=issues,
        )

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return _failure_result(
            repository=repository,
            file_path=path,
            issues=issues,
            severity="error",
            code="open_failed",
            detail=str(exc),
            exists=True,
        )

    with closing(conn):
        with conn:
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
            ).fetchone()
            if table_row is None:
                return _failure_result(
                    repository=repository,
                    file_path=path,
                    issues=issues,
                    severity="error",
                    code="missing_table",
                    detail="notifications",
                    exists=True,
                )

            column_rows = conn.execute("PRAGMA table_info(notifications)").fetchall()
            columns = {str(row["name"]) for row in column_rows}
            missing_columns = sorted(REQUIRED_SQLITE_COLUMNS - columns)
            if missing_columns:
                return _failure_result(
                    repository=repository,
                    file_path=path,
                    issues=issues,
                    severity="error",
                    code="missing_columns",
                    detail=",".join(missing_columns),
                    exists=True,
                )

            count_row = conn.execute("SELECT COUNT(*) AS count FROM notifications").fetchone()
            sent_row = conn.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE sent = 1"
            ).fetchone()
            pending_row = conn.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE sent = 0"
            ).fetchone()
            records = int(count_row["count"]) if count_row else 0
            sent = int(sent_row["count"]) if sent_row else 0
            pending = int(pending_row["count"]) if pending_row else 0

            invalid_sent = conn.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE sent NOT IN (0, 1)"
            ).fetchone()
            if invalid_sent and int(invalid_sent["count"]) > 0:
                issues.append(
                    _issue(repository, "error", "invalid_sent_value", str(invalid_sent["count"]))
                )

            invalid_required = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM notifications
                WHERE event_id IS NULL OR TRIM(event_id) = ''
                   OR area_code IS NULL OR TRIM(area_code) = ''
                   OR message IS NULL OR TRIM(message) = ''
                """
            ).fetchone()
            if invalid_required and int(invalid_required["count"]) > 0:
                issues.append(
                    _issue(
                        repository,
                        "error",
                        "invalid_required_field",
                        str(invalid_required["count"]),
                    )
                )

            timestamp_rows = conn.execute(
                "SELECT event_id, first_seen_at, updated_at, last_sent_at FROM notifications"
            ).fetchall()
            invalid_timestamps = 0
            for row in timestamp_rows:
                if parse_iso_to_utc(row["first_seen_at"]) is None:
                    invalid_timestamps += 1
                    continue
                if parse_iso_to_utc(row["updated_at"]) is None:
                    invalid_timestamps += 1
                    continue
                if (
                    row["last_sent_at"] is not None
                    and parse_iso_to_utc(row["last_sent_at"]) is None
                ):
                    invalid_timestamps += 1
            if invalid_timestamps > 0:
                issues.append(
                    _issue(repository, "error", "invalid_timestamp", str(invalid_timestamps))
                )

    return (
        _summary(
            repository=repository,
            file_path=path,
            exists=True,
            records=records,
            sent=sent,
            pending=pending,
        ),
        issues,
    )


def verify_state_files(
    *,
    json_state_file: Path,
    sqlite_state_file: Path,
    strict: bool = False,
) -> StateVerificationReport:
    json_summary, json_issues = verify_json_state(json_state_file, strict=strict)
    sqlite_summary, sqlite_issues = verify_sqlite_state(sqlite_state_file, strict=strict)
    return StateVerificationReport(
        summaries=[json_summary, sqlite_summary],
        issues=json_issues + sqlite_issues,
    )
