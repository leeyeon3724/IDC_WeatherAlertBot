from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.health import ApiHealthDecision
from app.domain.health_message_builder import build_health_notification_message
from app.entrypoints.runtime_builder import ServiceRuntime
from app.logging_utils import log_event, redact_sensitive_text
from app.observability import events
from app.services.notifier import NotificationError
from app.usecases.process_cycle import CycleStats

MIN_EXCEPTION_BACKOFF_SEC = 1


def _is_fatal_cycle_exception(exc: Exception) -> bool:
    return isinstance(exc, MemoryError)


def _maybe_close_resource(runtime: ServiceRuntime, resource_name: str) -> None:
    resource = getattr(runtime, resource_name, None)
    close_fn = getattr(resource, "close", None)
    if not callable(close_fn):
        return
    try:
        close_fn()
    except Exception:
        # Closing runtime resources is best-effort; shutdown path must not fail here.
        return


def close_runtime_resources(runtime: ServiceRuntime) -> None:
    _maybe_close_resource(runtime, "processor")
    _maybe_close_resource(runtime, "notifier")


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
                incident_duration_sec=health_decision.incident_duration_sec,
                incident_failed_cycles=health_decision.incident_failed_cycles,
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
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    pending_window = _get_persisted_backfill_window(runtime=runtime)
    if health_decision.event == "recovered":
        planned_window = _build_recovery_backfill_window(
            today=today,
            lookback_days=settings.lookback_days,
            max_backfill_days=settings.health_recovery_backfill_max_days,
            incident_duration_sec=health_decision.incident_duration_sec,
        )
        pending_window = _merge_backfill_windows(pending_window, planned_window)
        if pending_window is not None:
            _set_persisted_backfill_window(
                runtime=runtime,
                start_date=pending_window[0],
                end_date=pending_window[1],
            )

    if pending_window is None:
        return

    pending_start, pending_end = pending_window
    pending_start_date = _parse_compact_date(pending_start)
    pending_end_date = _parse_compact_date(pending_end)
    if (
        pending_start_date is None
        or pending_end_date is None
        or pending_start_date >= pending_end_date
    ):
        _set_persisted_backfill_window(runtime=runtime, start_date=None, end_date=None)
        return

    backfill_extra_days = (pending_end_date - pending_start_date).days
    if backfill_extra_days <= 0:
        _set_persisted_backfill_window(runtime=runtime, start_date=None, end_date=None)
        return

    window_days = max(1, settings.health_recovery_backfill_window_days)
    max_windows = max(1, settings.health_recovery_backfill_max_windows_per_cycle)
    lookback_days = max(0, (today - pending_start_date).days)
    runtime.logger.info(
        log_event(
            events.HEALTH_BACKFILL_START,
            lookback_days=lookback_days,
            incident_duration_sec=health_decision.incident_duration_sec,
            backfill_extra_days=backfill_extra_days,
            window_days=window_days,
            max_windows=max_windows,
        )
    )
    processed_days = 0
    processed_windows = 0
    sent_count = 0
    pending_total = runtime.state_repo.pending_count
    remaining_days = backfill_extra_days
    cursor_date = pending_start_date
    try:
        run_date_range = getattr(runtime.processor, "run_date_range", None)
        if callable(run_date_range):
            windows = _build_backfill_date_windows_from_range(
                start_date=pending_start,
                end_date=pending_end,
                window_days=window_days,
            )
            for start_date, end_date, days in windows[:max_windows]:
                backfill_stats = run_date_range(start_date=start_date, end_date=end_date)
                processed_windows += 1
                processed_days += days
                sent_count += backfill_stats.sent_count
                pending_total = backfill_stats.pending_total
                parsed_end = _parse_compact_date(end_date)
                if parsed_end is not None:
                    cursor_date = parsed_end
            remaining_days = max(0, (pending_end_date - cursor_date).days)
        else:
            backfill_stats = runtime.processor.run_once(lookback_days_override=lookback_days)
            processed_days = backfill_extra_days
            processed_windows = 1
            sent_count = backfill_stats.sent_count
            pending_total = backfill_stats.pending_total
            cursor_date = pending_end_date
            remaining_days = 0

        if remaining_days > 0:
            _set_persisted_backfill_window(
                runtime=runtime,
                start_date=_format_compact_date(cursor_date),
                end_date=pending_end,
            )
        else:
            _set_persisted_backfill_window(runtime=runtime, start_date=None, end_date=None)

        runtime.logger.info(
            log_event(
                events.HEALTH_BACKFILL_COMPLETE,
                lookback_days=lookback_days,
                sent_count=sent_count,
                pending_total=pending_total,
                backfill_extra_days=backfill_extra_days,
                processed_days=processed_days,
                remaining_days=remaining_days,
                processed_windows=processed_windows,
                window_days=window_days,
                max_windows=max_windows,
            )
        )
    except Exception as exc:
        remaining_days = max(0, (pending_end_date - cursor_date).days)
        if remaining_days > 0:
            _set_persisted_backfill_window(
                runtime=runtime,
                start_date=_format_compact_date(cursor_date),
                end_date=pending_end,
            )
        else:
            _set_persisted_backfill_window(runtime=runtime, start_date=None, end_date=None)
        runtime.logger.error(
            log_event(
                events.HEALTH_BACKFILL_FAILED,
                lookback_days=lookback_days,
                backfill_extra_days=backfill_extra_days,
                processed_days=processed_days,
                remaining_days=remaining_days,
                processed_windows=processed_windows,
                error=redact_sensitive_text(exc),
            )
        )


def _build_recovery_backfill_window(
    *,
    today: date,
    lookback_days: int,
    max_backfill_days: int,
    incident_duration_sec: int,
) -> tuple[str, str] | None:
    if max_backfill_days <= lookback_days:
        return None

    outage_days = max(1, math.ceil(incident_duration_sec / 86400))
    backfill_days = min(outage_days, max_backfill_days)
    if backfill_days <= lookback_days:
        return None

    current_start = today - timedelta(days=max(lookback_days, 0))
    backfill_start = today - timedelta(days=max(backfill_days, 0))
    if backfill_start >= current_start:
        return None
    return _format_compact_date(backfill_start), _format_compact_date(current_start)


def _build_backfill_date_windows(
    *,
    today: date,
    lookback_days: int,
    backfill_days: int,
    window_days: int,
) -> list[tuple[str, str, int]]:
    if backfill_days <= lookback_days:
        return []
    current_start = today - timedelta(days=max(lookback_days, 0))
    backfill_start = today - timedelta(days=max(backfill_days, 0))
    return _build_backfill_date_windows_from_range(
        start_date=_format_compact_date(backfill_start),
        end_date=_format_compact_date(current_start),
        window_days=window_days,
    )


def _build_backfill_date_windows_from_range(
    *,
    start_date: str,
    end_date: str,
    window_days: int,
) -> list[tuple[str, str, int]]:
    start = _parse_compact_date(start_date)
    end = _parse_compact_date(end_date)
    if start is None or end is None or start >= end:
        return []

    windows: list[tuple[str, str, int]] = []
    cursor = start
    step_days = max(1, window_days)
    while cursor < end:
        next_cursor = min(cursor + timedelta(days=step_days), end)
        windows.append(
            (
                _format_compact_date(cursor),
                _format_compact_date(next_cursor),
                (next_cursor - cursor).days,
            )
        )
        cursor = next_cursor
    return windows


def _merge_backfill_windows(
    first: tuple[str, str] | None,
    second: tuple[str, str] | None,
) -> tuple[str, str] | None:
    if first is None:
        return second
    if second is None:
        return first

    first_start, first_end = first
    second_start, second_end = second
    merged_start = min(first_start, second_start)
    merged_end = max(first_end, second_end)
    if merged_start >= merged_end:
        return None
    return merged_start, merged_end


def _get_persisted_backfill_window(*, runtime: ServiceRuntime) -> tuple[str, str] | None:
    getter = getattr(runtime.health_monitor, "get_recovery_backfill_window", None)
    if not callable(getter):
        return None
    window = getter()
    if window is None:
        return None
    start_date, end_date = window
    if _parse_compact_date(start_date) is None or _parse_compact_date(end_date) is None:
        return None
    if start_date >= end_date:
        return None
    return start_date, end_date


def _set_persisted_backfill_window(
    *,
    runtime: ServiceRuntime,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    setter = getattr(runtime.health_monitor, "set_recovery_backfill_window", None)
    if not callable(setter):
        return False
    setter(start_date=start_date, end_date=end_date)
    return True


def _parse_compact_date(value: str) -> date | None:
    text = value.strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        year = int(text[0:4])
        month = int(text[4:6])
        day = int(text[6:8])
        return date(year, month, day)
    except ValueError:
        return None


def _format_compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


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
            try:
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
                runtime.logger.info(
                    log_event(
                        events.CYCLE_COST_METRICS,
                        api_fetch_calls=stats.api_fetch_calls,
                        alerts_fetched=stats.alerts_fetched,
                        notification_attempts=stats.notification_attempts,
                        notification_sent=stats.sent_count,
                        notification_failures=stats.send_failures,
                        notification_dry_run_skips=stats.notification_dry_run_skips,
                        notification_backpressure_skips=stats.notification_backpressure_skips,
                        pending_total=stats.pending_total,
                    )
                )
                if runtime.settings.run_once:
                    runtime.logger.info(log_event(events.SHUTDOWN_RUN_ONCE_COMPLETE))
                    return 0
                sleep_until_next_cycle(
                    runtime=runtime,
                    health_decision=health_decision,
                    sleep_fn=sleep_fn,
                )
            except Exception as exc:
                if runtime.settings.run_once or _is_fatal_cycle_exception(exc):
                    runtime.logger.critical(
                        log_event(
                            events.CYCLE_FATAL_ERROR,
                            error=redact_sensitive_text(exc),
                        ),
                        exc_info=True,
                    )
                    return 1

                runtime.logger.error(
                    log_event(
                        events.CYCLE_ITERATION_FAILED,
                        error=redact_sensitive_text(exc),
                    ),
                    exc_info=True,
                )
                backoff_sec = max(runtime.settings.cycle_interval_sec, MIN_EXCEPTION_BACKOFF_SEC)
                sleep_fn(float(backoff_sec))
    except KeyboardInterrupt:
        runtime.logger.info(log_event(events.SHUTDOWN_INTERRUPT))
        return 0
    except Exception as exc:  # pragma: no cover
        runtime.logger.critical(
            log_event(events.SHUTDOWN_UNEXPECTED_ERROR, error=redact_sensitive_text(exc)),
            exc_info=True,
        )
        return 1
    finally:
        close_runtime_resources(runtime)
