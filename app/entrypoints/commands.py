from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

from app.entrypoints.runtime_builder import ServiceRuntime
from app.logging_utils import log_event, setup_logging
from app.observability import events
from app.repositories.json_state_repo import JsonStateRepository
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
        bootstrap_logger.critical(log_event(events.STARTUP_INVALID_CONFIG, error=str(exc)))
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
) -> int:
    logger = setup_logging_fn(log_level=log_level, timezone=timezone)
    repo = json_repo_factory(Path(state_file), logger=logger.getChild("state"))
    removed = repo.cleanup_stale(days=days, include_unsent=include_unsent, dry_run=dry_run)
    logger.info(
        log_event(
            events.STATE_CLEANUP_COMPLETE,
            state_file=state_file,
            days=days,
            include_unsent=include_unsent,
            dry_run=dry_run,
            removed=removed,
            total=repo.total_count,
            pending=repo.pending_count,
        )
    )
    return 0


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
    return parser
