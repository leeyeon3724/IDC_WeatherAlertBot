from __future__ import annotations

import argparse
import math
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.domain.health import HealthPolicy
from app.domain.health_message_builder import build_health_notification_message
from app.logging_utils import log_event, setup_logging
from app.repositories.health_state_repo import JsonHealthStateRepository
from app.repositories.state_repo import JsonStateRepository
from app.services.notifier import DoorayNotifier, NotificationError
from app.services.weather_api import WeatherAlertClient
from app.settings import Settings, SettingsError
from app.usecases.health_monitor import ApiHealthMonitor
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

    logger.info(
        log_event(
            "startup.ready",
            state_file=str(settings.sent_messages_file),
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

    last_cleanup_date: str | None = None
    try:
        while True:
            if settings.cleanup_enabled and not settings.dry_run:
                current_date = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")
                if current_date != last_cleanup_date:
                    removed = state_repo.cleanup_stale(
                        days=settings.cleanup_retention_days,
                        include_unsent=settings.cleanup_include_unsent,
                    )
                    logger.info(
                        log_event(
                            "state.cleanup.auto",
                            date=current_date,
                            days=settings.cleanup_retention_days,
                            include_unsent=settings.cleanup_include_unsent,
                            removed=removed,
                            total=state_repo.total_count,
                            pending=state_repo.pending_count,
                        )
                    )
                    last_cleanup_date = current_date

            stats = processor.run_once()
            health_decision = health_monitor.observe_cycle(
                now=datetime.now(UTC),
                total_areas=stats.area_count,
                failed_areas=stats.area_failures,
                error_counts=stats.api_error_counts,
                representative_error=stats.last_api_error,
            )
            logger.info(
                log_event(
                    "health.evaluate",
                    incident_open=health_decision.incident_open,
                    health_event=health_decision.event,
                    should_notify=health_decision.should_notify,
                    outage_window_fail_ratio=round(health_decision.outage_window_fail_ratio, 4),
                    recovery_window_fail_ratio=round(health_decision.recovery_window_fail_ratio, 4),
                    consecutive_severe_failures=health_decision.consecutive_severe_failures,
                    consecutive_stable_successes=health_decision.consecutive_stable_successes,
                )
            )
            if (
                settings.health_alert_enabled
                and health_decision.should_notify
                and not settings.dry_run
                and health_decision.event
            ):
                health_message = build_health_notification_message(health_decision)
                if health_message:
                    try:
                        notifier.send(health_message)
                        logger.info(
                            log_event(
                                "health.notification.sent",
                                health_event=health_decision.event,
                            )
                        )
                    except NotificationError as exc:
                        logger.error(
                            log_event(
                                "health.notification.failed",
                                health_event=health_decision.event,
                                attempts=exc.attempts,
                                error=str(exc.last_error or exc),
                            )
                        )
            if (
                health_decision.event == "recovered"
                and settings.health_recovery_backfill_max_days > settings.lookback_days
            ):
                outage_days = max(1, math.ceil(health_decision.incident_duration_sec / 86400))
                backfill_days = min(outage_days, settings.health_recovery_backfill_max_days)
                if backfill_days > settings.lookback_days:
                    logger.info(
                        log_event(
                            "health.backfill.start",
                            lookback_days=backfill_days,
                            incident_duration_sec=health_decision.incident_duration_sec,
                        )
                    )
                    try:
                        backfill_stats = processor.run_once(lookback_days_override=backfill_days)
                        logger.info(
                            log_event(
                                "health.backfill.complete",
                                lookback_days=backfill_days,
                                sent_count=backfill_stats.sent_count,
                                pending_total=backfill_stats.pending_total,
                            )
                        )
                    except Exception as exc:
                        logger.error(
                            log_event(
                                "health.backfill.failed",
                                lookback_days=backfill_days,
                                error=str(exc),
                            )
                        )
            logger.info(log_event("cycle.complete", **asdict(stats)))
            if settings.run_once:
                logger.info(log_event("shutdown.run_once_complete"))
                return 0
            sleep_sec = health_monitor.suggested_cycle_interval_sec(settings.cycle_interval_sec)
            if sleep_sec > 0:
                if sleep_sec != settings.cycle_interval_sec:
                    logger.info(
                        log_event(
                            "cycle.interval.adjusted",
                            base_interval_sec=settings.cycle_interval_sec,
                            adjusted_interval_sec=sleep_sec,
                            incident_open=health_decision.incident_open,
                        )
                    )
                time.sleep(sleep_sec)
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
