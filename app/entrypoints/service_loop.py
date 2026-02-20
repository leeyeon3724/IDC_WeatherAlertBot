from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.domain.health import ApiHealthDecision
from app.domain.health_message_builder import build_health_notification_message
from app.entrypoints.runtime_builder import ServiceRuntime
from app.logging_utils import log_event, redact_sensitive_text
from app.observability import events
from app.services.notifier import NotificationError
from app.usecases.process_cycle import CycleStats


def maybe_auto_cleanup(
    *,
    runtime: ServiceRuntime,
    last_cleanup_date: str | None,
    current_date: str,
) -> str | None:
    settings = runtime.settings
    if not settings.cleanup_enabled or settings.dry_run:
        return last_cleanup_date
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


def evaluate_health(
    *,
    runtime: ServiceRuntime,
    stats: CycleStats,
    now: datetime,
) -> ApiHealthDecision:
    decision = runtime.health_monitor.observe_cycle(
        now=now,
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


def maybe_send_health_notification(
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
                error=redact_sensitive_text(exc.last_error or exc),
            )
        )


def maybe_run_recovery_backfill(
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
                error=redact_sensitive_text(exc),
            )
        )


def sleep_until_next_cycle(
    *,
    runtime: ServiceRuntime,
    health_decision: ApiHealthDecision,
    sleep_fn: Callable[[float], None] = time.sleep,
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
    sleep_fn(float(sleep_sec))


def run_loop(
    runtime: ServiceRuntime,
    *,
    now_utc_fn: Callable[[], datetime] | None = None,
    now_local_date_fn: Callable[[str], str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    utc_now = now_utc_fn or (lambda: datetime.now(UTC))
    local_date = now_local_date_fn or (
        lambda timezone: datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d")
    )
    last_cleanup_date: str | None = None
    try:
        while True:
            last_cleanup_date = maybe_auto_cleanup(
                runtime=runtime,
                last_cleanup_date=last_cleanup_date,
                current_date=local_date(runtime.settings.timezone),
            )
            stats = runtime.processor.run_once()
            health_decision = evaluate_health(runtime=runtime, stats=stats, now=utc_now())
            maybe_send_health_notification(runtime=runtime, health_decision=health_decision)
            maybe_run_recovery_backfill(runtime=runtime, health_decision=health_decision)

            runtime.logger.info(log_event(events.CYCLE_COMPLETE, **asdict(stats)))
            if runtime.settings.run_once:
                runtime.logger.info(log_event(events.SHUTDOWN_RUN_ONCE_COMPLETE))
                return 0
            sleep_until_next_cycle(
                runtime=runtime,
                health_decision=health_decision,
                sleep_fn=sleep_fn,
            )
    except KeyboardInterrupt:
        runtime.logger.info(log_event(events.SHUTDOWN_INTERRUPT))
        return 0
    except Exception as exc:  # pragma: no cover
        runtime.logger.critical(
            log_event(events.SHUTDOWN_UNEXPECTED_ERROR, error=redact_sensitive_text(exc)),
            exc_info=True,
        )
        return 1
