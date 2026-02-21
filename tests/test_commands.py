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
        days=30,
        include_unsent=False,
        dry_run=False,
        setup_logging_fn=lambda **kwargs: logger,
        json_repo_factory=_failing_factory,
        state_repository_type="json",
        json_state_file="./data/state.json",
    )

    assert result == 1
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_CLEANUP_FAILED
    assert payload["state_file"] == "./data/state.json"
    assert "disk unavailable" in payload["error"]


def test_cleanup_state_uses_sqlite_repo_when_configured(tmp_path: Path) -> None:
    logger, handler = _captured_logger("test.commands.cleanup.sqlite")
    sqlite_file = tmp_path / "state.db"
    captured: dict[str, object] = {}

    class _FakeSqliteRepo:
        def __init__(self) -> None:
            self.total_count = 12
            self.pending_count = 3

        def cleanup_stale(
            self,
            *,
            days: int,
            include_unsent: bool,
            dry_run: bool,
            now=None,
        ) -> int:
            captured["days"] = days
            captured["include_unsent"] = include_unsent
            captured["dry_run"] = dry_run
            return 4

    def _fake_sqlite_factory(file_path: Path, logger: logging.Logger | None = None):
        captured["file_path"] = file_path
        return _FakeSqliteRepo()

    result = commands.cleanup_state(
        json_state_file="./data/state.json",
        sqlite_state_file=str(sqlite_file),
        state_repository_type="sqlite",
        days=30,
        include_unsent=False,
        dry_run=False,
        setup_logging_fn=lambda **kwargs: logger,
        sqlite_repo_factory=_fake_sqlite_factory,
    )

    assert result == 0
    assert captured["file_path"] == sqlite_file
    assert captured["days"] == 30
    assert captured["include_unsent"] is False
    assert captured["dry_run"] is False

    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_CLEANUP_COMPLETE
    assert payload["state_file"] == str(sqlite_file)
    assert payload["removed"] == 4
    assert payload["total"] == 12
    assert payload["pending"] == 3


def test_cleanup_state_uses_json_repo_when_configured(tmp_path: Path) -> None:
    logger, handler = _captured_logger("test.commands.cleanup.json")
    json_file = tmp_path / "state.json"
    captured: dict[str, object] = {}

    class _FakeJsonRepo:
        def __init__(self) -> None:
            self.total_count = 9
            self.pending_count = 1

        def cleanup_stale(
            self,
            *,
            days: int,
            include_unsent: bool,
            dry_run: bool,
            now=None,
        ) -> int:
            captured["days"] = days
            captured["include_unsent"] = include_unsent
            captured["dry_run"] = dry_run
            return 2

    def _fake_json_factory(file_path: Path, logger: logging.Logger | None = None):
        captured["file_path"] = file_path
        return _FakeJsonRepo()

    result = commands.cleanup_state(
        state_repository_type="json",
        json_state_file=str(json_file),
        sqlite_state_file="./data/ignored.db",
        days=30,
        include_unsent=True,
        dry_run=True,
        setup_logging_fn=lambda **kwargs: logger,
        json_repo_factory=_fake_json_factory,
    )

    assert result == 0
    assert captured["file_path"] == json_file
    assert captured["days"] == 30
    assert captured["include_unsent"] is True
    assert captured["dry_run"] is True

    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_CLEANUP_COMPLETE
    assert payload["state_file"] == str(json_file)
    assert payload["removed"] == 2
    assert payload["total"] == 9
    assert payload["pending"] == 1


def test_cleanup_state_returns_1_when_repository_type_is_invalid() -> None:
    logger, handler = _captured_logger("test.commands.cleanup.invalid_repo_type")

    result = commands.cleanup_state(
        state_repository_type="postgres",
        json_state_file="./data/state.json",
        sqlite_state_file="./data/state.db",
        days=30,
        include_unsent=False,
        dry_run=False,
        setup_logging_fn=lambda **kwargs: logger,
    )

    assert result == 1
    payload = json.loads(handler.messages[-1])
    assert payload["event"] == events.STATE_CLEANUP_FAILED
    assert payload["state_file"] == "./data/state.json"
    assert "state_repository_type must be one of: json, sqlite" in payload["error"]


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
