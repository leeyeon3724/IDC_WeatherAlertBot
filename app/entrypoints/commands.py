from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

from app.entrypoints.runtime_builder import ServiceRuntime
from app.logging_utils import log_event, redact_sensitive_text, setup_logging
from app.observability import events
from app.repositories.json_state_repo import JsonStateRepository
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_migration import JsonToSqliteMigrationResult, migrate_json_to_sqlite
from app.repositories.state_repository import StateRepository
from app.repositories.state_verifier import verify_state_files
from app.settings import Settings, SettingsError


def run_service(
    *,
    settings_from_env: Callable[..., Settings] = Settings.from_env,
    setup_logging_fn: Callable[..., logging.Logger] = setup_logging,
    build_runtime_fn: Callable[[Settings], ServiceRuntime],
    log_startup_fn: Callable[[ServiceRuntime], None],
    run_loop_fn: Callable[[ServiceRuntime], int],
) -> int:
    bootstrap_logger = setup_logging_fn()
    try:
        settings = settings_from_env()
    except SettingsError as exc:
        bootstrap_logger.critical(
            log_event(events.STARTUP_INVALID_CONFIG, error=redact_sensitive_text(exc))
        )
        return 1

    runtime = build_runtime_fn(settings)
    log_startup_fn(runtime)
    return run_loop_fn(runtime)


def cleanup_state(
    state_file: str,
    days: int,
    include_unsent: bool,
    dry_run: bool,
    *,
    log_level: str = "INFO",
    timezone: str = "Asia/Seoul",
    setup_logging_fn: Callable[..., logging.Logger] = setup_logging,
    json_repo_factory: Callable[..., JsonStateRepository] = JsonStateRepository,
    sqlite_repo_factory: Callable[..., SqliteStateRepository] = SqliteStateRepository,
    state_repository_type: str = "json",
    sqlite_state_file: str = "./data/sent_messages.db",
) -> int:
    logger = setup_logging_fn(log_level=log_level, timezone=timezone)
    target_state_file = state_file
    try:
        repo: StateRepository
        if state_repository_type == "sqlite":
            target_state_file = sqlite_state_file
            repo = sqlite_repo_factory(Path(sqlite_state_file), logger=logger.getChild("state"))
        else:
            repo = json_repo_factory(Path(state_file), logger=logger.getChild("state"))
        removed = repo.cleanup_stale(days=days, include_unsent=include_unsent, dry_run=dry_run)
    except Exception as exc:
        logger.error(
            log_event(
                events.STATE_CLEANUP_FAILED,
                state_file=target_state_file,
                days=days,
                include_unsent=include_unsent,
                dry_run=dry_run,
                error=redact_sensitive_text(exc),
            )
        )
        return 1

    logger.info(
        log_event(
            events.STATE_CLEANUP_COMPLETE,
            state_file=target_state_file,
            days=days,
            include_unsent=include_unsent,
            dry_run=dry_run,
            removed=removed,
            total=repo.total_count,
            pending=repo.pending_count,
        )
    )
    return 0


def migrate_state(
    json_state_file: str,
    sqlite_state_file: str,
    *,
    log_level: str = "INFO",
    timezone: str = "Asia/Seoul",
    setup_logging_fn: Callable[..., logging.Logger] = setup_logging,
    migrate_fn: Callable[..., JsonToSqliteMigrationResult] = migrate_json_to_sqlite,
) -> int:
    logger = setup_logging_fn(log_level=log_level, timezone=timezone)
    try:
        result = migrate_fn(
            json_state_file=Path(json_state_file),
            sqlite_state_file=Path(sqlite_state_file),
            logger=logger.getChild("migration"),
        )
    except Exception as exc:
        logger.error(
            log_event(
                events.STATE_MIGRATION_FAILED,
                json_state_file=json_state_file,
                sqlite_state_file=sqlite_state_file,
                error=redact_sensitive_text(exc),
            )
        )
        return 1

    logger.info(
        log_event(
            events.STATE_MIGRATION_COMPLETE,
            json_state_file=json_state_file,
            sqlite_state_file=sqlite_state_file,
            total_records=result.total_records,
            inserted_records=result.inserted_records,
            sent_records=result.sent_records,
            marked_sent_records=result.marked_sent_records,
        )
    )
    return 0


def verify_state(
    *,
    json_state_file: str,
    sqlite_state_file: str,
    strict: bool,
    log_level: str = "INFO",
    timezone: str = "Asia/Seoul",
    setup_logging_fn: Callable[..., logging.Logger] = setup_logging,
) -> int:
    logger = setup_logging_fn(log_level=log_level, timezone=timezone)
    try:
        report = verify_state_files(
            json_state_file=Path(json_state_file),
            sqlite_state_file=Path(sqlite_state_file),
            strict=strict,
        )
    except Exception as exc:
        logger.error(
            log_event(
                events.STATE_VERIFY_FAILED,
                json_state_file=json_state_file,
                sqlite_state_file=sqlite_state_file,
                strict=strict,
                error=redact_sensitive_text(exc),
            )
        )
        return 1

    payload = {
        "json_state_file": json_state_file,
        "sqlite_state_file": sqlite_state_file,
        "strict": strict,
        "passed": report.passed,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "summaries": [
            {
                "repository": summary.repository,
                "file_path": summary.file_path,
                "exists": summary.exists,
                "records": summary.records,
                "sent": summary.sent,
                "pending": summary.pending,
            }
            for summary in report.summaries
        ],
        "issues": [
            {
                "repository": issue.repository,
                "severity": issue.severity,
                "code": issue.code,
                "detail": issue.detail,
            }
            for issue in report.issues
        ],
    }
    if report.passed:
        logger.info(log_event(events.STATE_VERIFY_COMPLETE, **payload))
        return 0

    logger.error(log_event(events.STATE_VERIFY_FAILED, **payload))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weather alert bot")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run weather alert bot service")

    cleanup_parser = subparsers.add_parser(
        "cleanup-state",
        help="Delete stale entries from state file",
    )
    cleanup_parser.add_argument(
        "--state-file",
        default="./data/sent_messages.json",
        help="Path to state JSON file",
    )
    cleanup_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Delete entries older than this many days",
    )
    cleanup_parser.add_argument(
        "--include-unsent",
        action="store_true",
        help="Include unsent entries in cleanup",
    )
    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview removal count without persisting",
    )

    migration_parser = subparsers.add_parser(
        "migrate-state",
        help="Migrate JSON state file records into SQLite state DB",
    )
    migration_parser.add_argument(
        "--json-state-file",
        default="./data/sent_messages.json",
        help="Path to source JSON state file",
    )
    migration_parser.add_argument(
        "--sqlite-state-file",
        default="./data/sent_messages.db",
        help="Path to target SQLite DB file",
    )

    verify_parser = subparsers.add_parser(
        "verify-state",
        help="Verify JSON/SQLite state repository integrity",
    )
    verify_parser.add_argument(
        "--json-state-file",
        default="./data/sent_messages.json",
        help="Path to JSON state file",
    )
    verify_parser.add_argument(
        "--sqlite-state-file",
        default="./data/sent_messages.db",
        help="Path to SQLite state DB file",
    )
    verify_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing state files as verification errors",
    )
    return parser
