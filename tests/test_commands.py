from __future__ import annotations

import json
import logging
from pathlib import Path

from app.entrypoints import commands
from app.observability import events
from app.repositories.state_migration import JsonToSqliteMigrationResult


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
