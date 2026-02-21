from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.domain.health import HealthPolicy
from app.logging_utils import log_event, setup_logging
from app.observability import events
from app.repositories.health_state_repo import JsonHealthStateRepository
from app.repositories.json_state_repo import JsonStateRepository
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_repository import StateRepository
from app.services.notifier import DoorayNotifier
from app.services.weather_api import WeatherAlertClient
from app.settings import Settings
from app.usecases.health_monitor import ApiHealthMonitor
from app.usecases.process_cycle import ProcessCycleUseCase


@dataclass(frozen=True)
class ServiceRuntime:
    settings: Settings
    logger: logging.Logger
    state_repo: StateRepository
    notifier: DoorayNotifier
    processor: ProcessCycleUseCase
    health_monitor: ApiHealthMonitor


def build_state_repository(
    *,
    settings: Settings,
    logger: logging.Logger,
    json_repository_factory: Callable[..., StateRepository] = JsonStateRepository,
    sqlite_repository_factory: Callable[..., StateRepository] = SqliteStateRepository,
) -> StateRepository:
    if settings.state_repository_type == "sqlite":
        return sqlite_repository_factory(
            file_path=settings.sqlite_state_file,
            logger=logger.getChild("state"),
        )
    return json_repository_factory(
        file_path=settings.sent_messages_file,
        logger=logger.getChild("state"),
    )


def build_runtime(
    settings: Settings,
    *,
    setup_logging_fn: Callable[..., logging.Logger] = setup_logging,
    build_state_repository_fn: Callable[..., StateRepository] = build_state_repository,
    weather_client_factory: Callable[..., WeatherAlertClient] = WeatherAlertClient,
    notifier_factory: Callable[..., DoorayNotifier] = DoorayNotifier,
    processor_factory: Callable[..., ProcessCycleUseCase] = ProcessCycleUseCase,
    health_state_repository_factory: Callable[
        ...,
        JsonHealthStateRepository,
    ] = JsonHealthStateRepository,
    health_monitor_factory: Callable[..., ApiHealthMonitor] = ApiHealthMonitor,
) -> ServiceRuntime:
    logger = setup_logging_fn(settings.log_level, settings.timezone)
    state_repo = build_state_repository_fn(settings=settings, logger=logger)
    weather_client = weather_client_factory(
        settings=settings,
        logger=logger.getChild("weather_api"),
    )
    notifier = notifier_factory(
        hook_url=settings.service_hook_url,
        bot_name=settings.bot_name,
        timeout_sec=settings.notifier_timeout_sec,
        connect_timeout_sec=settings.notifier_connect_timeout_sec,
        read_timeout_sec=settings.notifier_read_timeout_sec,
        max_retries=settings.notifier_max_retries,
        retry_delay_sec=settings.notifier_retry_delay_sec,
        send_rate_limit_per_sec=settings.notifier_send_rate_limit_per_sec,
        circuit_breaker_enabled=settings.notifier_circuit_breaker_enabled,
        circuit_failure_threshold=settings.notifier_circuit_failure_threshold,
        circuit_reset_sec=settings.notifier_circuit_reset_sec,
        logger=logger.getChild("notifier"),
    )
    processor = processor_factory(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=state_repo,
        logger=logger.getChild("processor"),
    )
    health_state_repo = health_state_repository_factory(
        file_path=settings.health_state_file,
        logger=logger.getChild("health_state"),
    )
    health_monitor = health_monitor_factory(
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


def log_startup(runtime: ServiceRuntime) -> None:
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
            api_soft_rate_limit_per_sec=settings.api_soft_rate_limit_per_sec,
            notifier_send_rate_limit_per_sec=settings.notifier_send_rate_limit_per_sec,
            dry_run=settings.dry_run,
            run_once=settings.run_once,
            lookback_days=settings.lookback_days,
            health_alert_enabled=settings.health_alert_enabled,
            health_backoff_max_sec=settings.health_backoff_max_sec,
            health_recovery_backfill_max_days=settings.health_recovery_backfill_max_days,
            health_recovery_backfill_window_days=settings.health_recovery_backfill_window_days,
            health_recovery_backfill_max_windows_per_cycle=(
                settings.health_recovery_backfill_max_windows_per_cycle
            ),
            cleanup_enabled=settings.cleanup_enabled,
            cleanup_retention_days=settings.cleanup_retention_days,
            cleanup_include_unsent=settings.cleanup_include_unsent,
        )
    )
    missing_area_codes = [
        area_code
        for area_code in settings.area_codes
        if area_code not in settings.area_code_mapping
    ]
    if not missing_area_codes:
        return

    area_codes_count = len(settings.area_codes)
    mapped_count = max(area_codes_count - len(missing_area_codes), 0)
    coverage_pct = round((mapped_count / area_codes_count) * 100.0, 2) if area_codes_count else 0.0
    runtime.logger.warning(
        log_event(
            events.AREA_MAPPING_COVERAGE_WARNING,
            area_codes_count=area_codes_count,
            mapped_count=mapped_count,
            missing_count=len(missing_area_codes),
            missing_area_codes=missing_area_codes,
            coverage_pct=coverage_pct,
        )
    )
