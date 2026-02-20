from __future__ import annotations

import argparse
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.domain.health import ApiHealthDecision, HealthPolicy
from app.domain.health_message_builder import build_health_notification_message
from app.logging_utils import log_event, setup_logging
from app.observability import events
from app.repositories.health_state_repo import JsonHealthStateRepository
from app.repositories.json_state_repo import JsonStateRepository
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_repository import StateRepository
from app.services.notifier import DoorayNotifier, NotificationError
from app.services.weather_api import WeatherAlertClient
from app.settings import Settings, SettingsError
from app.usecases.health_monitor import ApiHealthMonitor
from app.usecases.process_cycle import CycleStats, ProcessCycleUseCase


@dataclass(frozen=True)
class ServiceRuntime:
    settings: Settings
    logger: logging.Logger
    state_repo: StateRepository
    notifier: DoorayNotifier
    processor: ProcessCycleUseCase
    health_monitor: ApiHealthMonitor


def _build_state_repository(settings: Settings, logger: logging.Logger) -> StateRepository:
    if settings.state_repository_type == "sqlite":
        return SqliteStateRepository(
            file_path=settings.sqlite_state_file,
            logger=logger.getChild("state"),
        )
    return JsonStateRepository(
        file_path=settings.sent_messages_file,
        logger=logger.getChild("state"),
    )


def _build_runtime(settings: Settings) -> ServiceRuntime:
    logger = setup_logging(settings.log_level, settings.timezone)
    state_repo = _build_state_repository(settings=settings, logger=logger)
    weather_client = WeatherAlertClient(
        settings=settings,
        logger=logger.getChild("weather_api"),
    )
    notifier = DoorayNotifier(
        hook_url=settings.service_hook_url,
        bot_name=settings.bot_name,
        timeout_sec=settings.notifier_timeout_sec,
        connect_timeout_sec=settings.notifier_connect_timeout_sec,
        read_timeout_sec=settings.notifier_read_timeout_sec,
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
    health_state_repo = JsonHealthStateRepository(
        file_path=settings.health_state_file,
        logger=logger.getChild("health_state"),
    )
    health_monitor = ApiHealthMonitor(
        state_repo=health_state_repo,
        policy=HealthPolicy(
            outage_window_sec=settings.health_outage_window_sec,
            outage_fail_ratio_threshold=settings.health_outage_fail_ratio_threshold,
            outage_min_failed_cycles=settings.health_outage_min_failed_cycles,
            outage_consecutive_failures=settings.health_outage_consecutive_failures,
            recovery_window_sec=settings.health_recovery_window_sec,
            recovery_max_fail_ratio=settings.health_recovery_max_fail_ratio,
            recovery_consecutive_successes=settings.health_recovery_consecutive_successes,
            heartbeat_interval_sec=settings.health_heartbeat_interval_sec,
            max_backoff_sec=settings.health_backoff_max_sec,
        ),
        logger=logger.getChild("health_monitor"),
    )
    return ServiceRuntime(
        settings=settings,
        logger=logger,
        state_repo=state_repo,
        notifier=notifier,
        processor=processor,
        health_monitor=health_monitor,
    )


def _log_startup(runtime: ServiceRuntime) -> None:
    settings = runtime.settings
    runtime.logger.info(
        log_event(
            events.STARTUP_READY,
            state_file=str(settings.sent_messages_file),
            state_repository_type=settings.state_repository_type,
            sqlite_state_file=str(settings.sqlite_state_file),
            health_state_file=str(settings.health_state_file),
            area_count=len(settings.area_codes),
            area_max_workers=settings.area_max_workers,
            dry_run=settings.dry_run,
            run_once=settings.run_once,
            lookback_days=settings.lookback_days,
            health_alert_enabled=settings.health_alert_enabled,
            health_backoff_max_sec=settings.health_backoff_max_sec,
            health_recovery_backfill_max_days=settings.health_recovery_backfill_max_days,
            cleanup_enabled=settings.cleanup_enabled,
            cleanup_retention_days=settings.cleanup_retention_days,
            cleanup_include_unsent=settings.cleanup_include_unsent,
        )
    )


def _maybe_auto_cleanup(
    *,
    runtime: ServiceRuntime,
    last_cleanup_date: str | None,
) -> str | None:
    settings = runtime.settings
    if not settings.cleanup_enabled or settings.dry_run:
        return last_cleanup_date

    current_date = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")
    if current_date == last_cleanup_date:
        return last_cleanup_date

    removed = runtime.state_repo.cleanup_stale(
        days=settings.cleanup_retention_days,
        include_unsent=settings.cleanup_include_unsent,
    )
    runtime.logger.info(
        log_event(
            events.STATE_CLEANUP_AUTO,
            date=current_date,
            days=settings.cleanup_retention_days,
            include_unsent=settings.cleanup_include_unsent,
            removed=removed,
            total=runtime.state_repo.total_count,
            pending=runtime.state_repo.pending_count,
        )
    )
    return current_date


def _evaluate_health(*, runtime: ServiceRuntime, stats: CycleStats) -> ApiHealthDecision:
    decision = runtime.health_monitor.observe_cycle(
        now=datetime.now(UTC),
        total_areas=stats.area_count,
        failed_areas=stats.area_failures,
        error_counts=stats.api_error_counts,
        representative_error=stats.last_api_error,
    )
    runtime.logger.info(
        log_event(
            events.HEALTH_EVALUATE,
            incident_open=decision.incident_open,
            health_event=decision.event,
            should_notify=decision.should_notify,
            outage_window_fail_ratio=round(decision.outage_window_fail_ratio, 4),
            recovery_window_fail_ratio=round(decision.recovery_window_fail_ratio, 4),
            consecutive_severe_failures=decision.consecutive_severe_failures,
            consecutive_stable_successes=decision.consecutive_stable_successes,
        )
    )
    return decision


def _maybe_send_health_notification(
    *,
    runtime: ServiceRuntime,
    health_decision: ApiHealthDecision,
) -> None:
    settings = runtime.settings
    if (
        not settings.health_alert_enabled
        or not health_decision.should_notify
        or settings.dry_run
        or not health_decision.event
    ):
        return

    health_message = build_health_notification_message(health_decision)
    if not health_message:
        return

    try:
        runtime.notifier.send(health_message)
        runtime.logger.info(
            log_event(
                events.HEALTH_NOTIFICATION_SENT,
                health_event=health_decision.event,
            )
        )
    except NotificationError as exc:
        runtime.logger.error(
            log_event(
                events.HEALTH_NOTIFICATION_FAILED,
                health_event=health_decision.event,
                attempts=exc.attempts,
                error=str(exc.last_error or exc),
            )
        )


def _maybe_run_recovery_backfill(
    *,
    runtime: ServiceRuntime,
    health_decision: ApiHealthDecision,
) -> None:
    settings = runtime.settings
    if (
        health_decision.event != "recovered"
        or settings.health_recovery_backfill_max_days <= settings.lookback_days
    ):
        return

    outage_days = max(1, math.ceil(health_decision.incident_duration_sec / 86400))
    backfill_days = min(outage_days, settings.health_recovery_backfill_max_days)
    if backfill_days <= settings.lookback_days:
        return

    runtime.logger.info(
        log_event(
            events.HEALTH_BACKFILL_START,
            lookback_days=backfill_days,
            incident_duration_sec=health_decision.incident_duration_sec,
        )
    )
    try:
        backfill_stats = runtime.processor.run_once(lookback_days_override=backfill_days)
        runtime.logger.info(
            log_event(
                events.HEALTH_BACKFILL_COMPLETE,
                lookback_days=backfill_days,
                sent_count=backfill_stats.sent_count,
                pending_total=backfill_stats.pending_total,
            )
        )
    except Exception as exc:
        runtime.logger.error(
            log_event(
                events.HEALTH_BACKFILL_FAILED,
                lookback_days=backfill_days,
                error=str(exc),
            )
        )


def _sleep_until_next_cycle(
    *,
    runtime: ServiceRuntime,
    health_decision: ApiHealthDecision,
) -> None:
    sleep_sec = runtime.health_monitor.suggested_cycle_interval_sec(
        runtime.settings.cycle_interval_sec
    )
    if sleep_sec <= 0:
        return

    if sleep_sec != runtime.settings.cycle_interval_sec:
        runtime.logger.info(
            log_event(
                events.CYCLE_INTERVAL_ADJUSTED,
                base_interval_sec=runtime.settings.cycle_interval_sec,
                adjusted_interval_sec=sleep_sec,
                incident_open=health_decision.incident_open,
            )
        )
    time.sleep(sleep_sec)


def _run_loop(runtime: ServiceRuntime) -> int:
    last_cleanup_date: str | None = None
    try:
        while True:
            last_cleanup_date = _maybe_auto_cleanup(
                runtime=runtime,
                last_cleanup_date=last_cleanup_date,
            )
            stats = runtime.processor.run_once()
            health_decision = _evaluate_health(runtime=runtime, stats=stats)
            _maybe_send_health_notification(runtime=runtime, health_decision=health_decision)
            _maybe_run_recovery_backfill(runtime=runtime, health_decision=health_decision)

            runtime.logger.info(log_event(events.CYCLE_COMPLETE, **asdict(stats)))
            if runtime.settings.run_once:
                runtime.logger.info(log_event(events.SHUTDOWN_RUN_ONCE_COMPLETE))
                return 0
            _sleep_until_next_cycle(runtime=runtime, health_decision=health_decision)
    except KeyboardInterrupt:
        runtime.logger.info(log_event(events.SHUTDOWN_INTERRUPT))
        return 0
    except Exception as exc:  # pragma: no cover
        runtime.logger.critical(
            log_event(events.SHUTDOWN_UNEXPECTED_ERROR, error=str(exc)),
            exc_info=True,
        )
        return 1


def _run_service() -> int:
    bootstrap_logger = setup_logging()
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        bootstrap_logger.critical(log_event(events.STARTUP_INVALID_CONFIG, error=str(exc)))
        return 1

    runtime = _build_runtime(settings)
    _log_startup(runtime)
    return _run_loop(runtime)


def _cleanup_state(state_file: str, days: int, include_unsent: bool, dry_run: bool) -> int:
    logger = setup_logging(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "Asia/Seoul"),
    )
    repo = JsonStateRepository(Path(state_file), logger=logger.getChild("state"))
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
