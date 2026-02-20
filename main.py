from __future__ import annotations

import argparse
import os
import time
from dataclasses import asdict
from pathlib import Path

from app.logging_utils import log_event, setup_logging
from app.repositories.state_repo import JsonStateRepository
from app.services.notifier import DoorayNotifier
from app.services.weather_api import WeatherAlertClient
from app.settings import Settings, SettingsError
from app.usecases.process_cycle import ProcessCycleUseCase


def _run_service() -> int:
    bootstrap_logger = setup_logging()
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        bootstrap_logger.critical(log_event("startup.invalid_config", error=str(exc)))
        return 1

    logger = setup_logging(settings.log_level, settings.timezone)
    state_repo = JsonStateRepository(
        file_path=settings.sent_messages_file,
        logger=logger.getChild("state"),
    )
    weather_client = WeatherAlertClient(
        settings=settings,
        logger=logger.getChild("weather_api"),
    )
    notifier = DoorayNotifier(
        hook_url=settings.service_hook_url,
        bot_name=settings.bot_name,
        timeout_sec=settings.request_timeout_sec,
        max_retries=settings.notifier_max_retries,
        retry_delay_sec=settings.notifier_retry_delay_sec,
        logger=logger.getChild("notifier"),
    )
    processor = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=state_repo,
        logger=logger.getChild("processor"),
    )

    logger.info(
        log_event(
            "startup.ready",
            state_file=str(settings.sent_messages_file),
            area_count=len(settings.area_codes),
            dry_run=settings.dry_run,
            run_once=settings.run_once,
        )
    )

    try:
        while True:
            stats = processor.run_once()
            logger.info(log_event("cycle.complete", **asdict(stats)))
            if settings.run_once:
                logger.info(log_event("shutdown.run_once_complete"))
                return 0
            if settings.cycle_interval_sec > 0:
                time.sleep(settings.cycle_interval_sec)
    except KeyboardInterrupt:
        logger.info(log_event("shutdown.interrupt"))
        return 0
    except Exception as exc:  # pragma: no cover
        logger.critical(
            log_event("shutdown.unexpected_error", error=str(exc)),
            exc_info=True,
        )
        return 1


def _cleanup_state(state_file: str, days: int, include_unsent: bool, dry_run: bool) -> int:
    logger = setup_logging(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "Asia/Seoul"),
    )
    repo = JsonStateRepository(Path(state_file), logger=logger.getChild("state"))
    removed = repo.cleanup_stale(days=days, include_unsent=include_unsent, dry_run=dry_run)
    logger.info(
        log_event(
            "state.cleanup.complete",
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


def _build_parser() -> argparse.ArgumentParser:
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "cleanup-state":
        if args.days < 0:
            parser.error("--days must be >= 0")
        return _cleanup_state(
            state_file=args.state_file,
            days=args.days,
            include_unsent=args.include_unsent,
            dry_run=args.dry_run,
        )

    return _run_service()


if __name__ == "__main__":
    raise SystemExit(main())
