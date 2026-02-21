from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.entrypoints import commands, runtime_builder, service_loop
from app.entrypoints.runtime_builder import ServiceRuntime
from app.logging_utils import setup_logging
from app.repositories.health_state_repo import JsonHealthStateRepository
from app.repositories.json_state_repo import JsonStateRepository
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_repository import StateRepository
from app.services.notifier import DoorayNotifier
from app.services.weather_api import WeatherAlertClient
from app.settings import Settings
from app.usecases.health_monitor import ApiHealthMonitor
from app.usecases.process_cycle import ProcessCycleUseCase


def _build_state_repository(settings: Settings, logger: logging.Logger) -> StateRepository:
    return runtime_builder.build_state_repository(
        settings=settings,
        logger=logger,
        json_repository_factory=JsonStateRepository,
        sqlite_repository_factory=SqliteStateRepository,
    )


def _build_runtime(settings: Settings) -> ServiceRuntime:
    return runtime_builder.build_runtime(
        settings,
        setup_logging_fn=setup_logging,
        build_state_repository_fn=_build_state_repository,
        weather_client_factory=WeatherAlertClient,
        notifier_factory=DoorayNotifier,
        processor_factory=ProcessCycleUseCase,
        health_state_repository_factory=JsonHealthStateRepository,
        health_monitor_factory=ApiHealthMonitor,
    )


def _log_startup(runtime: ServiceRuntime) -> None:
    runtime_builder.log_startup(runtime)


def _run_loop(runtime: ServiceRuntime) -> int:
    return service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime.now(UTC),
        now_local_date_fn=lambda timezone: datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d"),
        sleep_fn=time.sleep,
    )


def _run_service() -> int:
    return commands.run_service(
        settings_from_env=Settings.from_env,
        setup_logging_fn=setup_logging,
        build_runtime_fn=_build_runtime,
        log_startup_fn=_log_startup,
        run_loop_fn=_run_loop,
    )


def _cleanup_state(
    *,
    state_repository_type: str | None,
    json_state_file: str,
    sqlite_state_file: str,
    days: int,
    include_unsent: bool,
    dry_run: bool,
) -> int:
    resolved_repository_type = (
        state_repository_type
        if state_repository_type is not None
        else os.getenv("STATE_REPOSITORY_TYPE", "sqlite")
    ).strip().lower()
    return commands.cleanup_state(
        days=days,
        include_unsent=include_unsent,
        dry_run=dry_run,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "Asia/Seoul"),
        setup_logging_fn=setup_logging,
        json_repo_factory=JsonStateRepository,
        sqlite_repo_factory=SqliteStateRepository,
        state_repository_type=resolved_repository_type,
        json_state_file=json_state_file,
        sqlite_state_file=sqlite_state_file,
    )


def _migrate_state(json_state_file: str, sqlite_state_file: str) -> int:
    return commands.migrate_state(
        json_state_file=json_state_file,
        sqlite_state_file=sqlite_state_file,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "Asia/Seoul"),
        setup_logging_fn=setup_logging,
    )


def _verify_state(json_state_file: str, sqlite_state_file: str, strict: bool) -> int:
    return commands.verify_state(
        json_state_file=json_state_file,
        sqlite_state_file=sqlite_state_file,
        strict=strict,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "Asia/Seoul"),
        setup_logging_fn=setup_logging,
    )


def _build_parser() -> argparse.ArgumentParser:
    return commands.build_parser()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "cleanup-state":
        if args.days < 0:
            parser.error("--days must be >= 0")
        return _cleanup_state(
            state_repository_type=args.state_repository_type,
            json_state_file=args.json_state_file,
            sqlite_state_file=args.sqlite_state_file,
            days=args.days,
            include_unsent=args.include_unsent,
            dry_run=args.dry_run,
        )
    if command == "migrate-state":
        return _migrate_state(
            json_state_file=args.json_state_file,
            sqlite_state_file=args.sqlite_state_file,
        )
    if command == "verify-state":
        return _verify_state(
            json_state_file=args.json_state_file,
            sqlite_state_file=args.sqlite_state_file,
            strict=args.strict,
        )

    return _run_service()


if __name__ == "__main__":
    raise SystemExit(main())
