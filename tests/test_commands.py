from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from app.domain.models import AlertNotification
from app.entrypoints import commands
from app.observability import events
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_migration import JsonToSqliteMigrationResult
from app.repositories.state_models import utc_now_iso


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _captured_logger(name: str) -> tuple[logging.Logger, _CaptureHandler]:
    logger = logging.getLogger(name)
    logger.handlers = []
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _CaptureHandler()
    logger.addHandler(handler)
    return logger, handler


def test_cleanup_state_returns_1_and_logs_failed_event() -> None:
    logger, handler = _captured_logger("test.commands.cleanup.failed")

    def _failing_factory(file_path: Path, logger: logging.Logger | None = None):
        raise OSError("disk unavailable")

    result = commands.cleanup_state(
        state_file="./data/state.json",
        days=30,
        include_unsent=False,
        dry_run=False,
        setup_logging_fn=lambda **kwargs: logger,
        json_repo_factory=_failing_factory,
    )

    assert result == 1
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_CLEANUP_FAILED
    assert payload["state_file"] == "./data/state.json"
    assert "disk unavailable" in payload["error"]


def test_migrate_state_returns_1_and_logs_failed_event() -> None:
    logger, handler = _captured_logger("test.commands.migrate.failed")

    def _failing_migrate(*, json_state_file: Path, sqlite_state_file: Path, logger: logging.Logger):
        raise RuntimeError("migration broken")

    result = commands.migrate_state(
        json_state_file="./data/source.json",
        sqlite_state_file="./data/target.db",
        setup_logging_fn=lambda **kwargs: logger,
        migrate_fn=_failing_migrate,
    )

    assert result == 1
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_MIGRATION_FAILED
    assert payload["json_state_file"] == "./data/source.json"
    assert "migration broken" in payload["error"]


def test_migrate_state_returns_0_and_logs_complete_event() -> None:
    logger, handler = _captured_logger("test.commands.migrate.complete")

    def _successful_migrate(
        *,
        json_state_file: Path,
        sqlite_state_file: Path,
        logger: logging.Logger,
    ):
        return JsonToSqliteMigrationResult(
            total_records=3,
            inserted_records=2,
            sent_records=1,
            marked_sent_records=1,
        )

    result = commands.migrate_state(
        json_state_file="./data/source.json",
        sqlite_state_file="./data/target.db",
        setup_logging_fn=lambda **kwargs: logger,
        migrate_fn=_successful_migrate,
    )

    assert result == 0
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_MIGRATION_COMPLETE
    assert payload["total_records"] == 3
    assert payload["inserted_records"] == 2


def test_verify_state_returns_0_and_logs_complete_event(tmp_path: Path) -> None:
    logger, handler = _captured_logger("test.commands.verify.complete")
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

    result = commands.verify_state(
        json_state_file=str(json_state_file),
        sqlite_state_file=str(sqlite_state_file),
        strict=True,
        setup_logging_fn=lambda **kwargs: logger,
    )

    assert result == 0
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_VERIFY_COMPLETE
    assert payload["error_count"] == 0
    assert payload["warning_count"] == 0


def test_verify_state_returns_1_and_logs_failed_event_for_invalid_json(tmp_path: Path) -> None:
    logger, handler = _captured_logger("test.commands.verify.failed")
    json_state_file = tmp_path / "state.json"
    sqlite_state_file = tmp_path / "state.db"
    json_state_file.write_text("{invalid", encoding="utf-8")

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

    result = commands.verify_state(
        json_state_file=str(json_state_file),
        sqlite_state_file=str(sqlite_state_file),
        strict=True,
        setup_logging_fn=lambda **kwargs: logger,
    )

    assert result == 1
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_VERIFY_FAILED
    assert payload["error_count"] >= 1
