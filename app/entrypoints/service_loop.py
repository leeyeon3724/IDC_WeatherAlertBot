from __future__ import annotations

import signal
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.health import ApiHealthDecision
from app.domain.health_message_builder import build_health_notification_message
from app.entrypoints.backfill import maybe_run_recovery_backfill
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


def _resolve_signal_reason(signum: int | signal.Signals) -> str:
    try:
        signal_id = signum if isinstance(signum, signal.Signals) else signal.Signals(signum)
        return signal_id.name.lower()
    except ValueError:
        return "signal"


def _shutdown_timeout_sec(runtime: ServiceRuntime) -> int:
    return max(0, runtime.settings.shutdown_timeout_sec)


def _shutdown_elapsed_sec(shutdown_state: dict[str, Any]) -> float:
    requested_at = shutdown_state.get("requested_at_monotonic")
    if not isinstance(requested_at, float):
        return 0.0
    return max(0.0, time.monotonic() - requested_at)


def _request_shutdown(
    *,
    runtime: ServiceRuntime,
    shutdown_state: dict[str, Any],
    reason: str,
) -> None:
    if shutdown_state["requested"]:
        return

    timeout_sec = _shutdown_timeout_sec(runtime)
    shutdown_state["requested"] = True
    shutdown_state["reason"] = reason
    shutdown_state["requested_at_monotonic"] = time.monotonic()
    shutdown_state["forced"] = False

    runtime.logger.info(log_event(events.SHUTDOWN_INTERRUPT))
    runtime.logger.info(
        log_event(
            events.SHUTDOWN_START,
            reason=reason,
            timeout_sec=timeout_sec,
        )
    )


def _maybe_force_shutdown(
    *,
    runtime: ServiceRuntime,
    shutdown_state: dict[str, Any],
) -> bool:
    if not shutdown_state["requested"] or shutdown_state["forced"]:
        return False

    timeout_sec = _shutdown_timeout_sec(runtime)
    if timeout_sec <= 0:
        return False

    elapsed_sec = _shutdown_elapsed_sec(shutdown_state)
    if elapsed_sec < float(timeout_sec):
        return False

    shutdown_state["forced"] = True
    runtime.logger.warning(
        log_event(
            events.SHUTDOWN_FORCED,
            reason=shutdown_state.get("reason", "unknown"),
            timeout_sec=timeout_sec,
            elapsed_sec=round(elapsed_sec, 3),
        )
    )
    return True


def _log_shutdown_complete(*, runtime: ServiceRuntime, shutdown_state: dict[str, Any]) -> None:
    if not shutdown_state["requested"]:
        return

    runtime.logger.info(
        log_event(
            events.SHUTDOWN_COMPLETE,
            reason=shutdown_state.get("reason", "unknown"),
            elapsed_sec=round(_shutdown_elapsed_sec(shutdown_state), 3),
            forced=bool(shutdown_state.get("forced", False)),
        )
    )


def _install_shutdown_signal_handlers(
    *,
    runtime: ServiceRuntime,
    shutdown_state: dict[str, Any],
) -> Callable[[], None]:
    previous_handlers: dict[signal.Signals, Any] = {}

    def _mark_shutdown(signum: int, _frame: Any) -> None:
        _request_shutdown(
            runtime=runtime,
            shutdown_state=shutdown_state,
            reason=_resolve_signal_reason(signum),
        )

    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, _mark_shutdown)
    except (ValueError, OSError):
        return lambda: None

    def _restore() -> None:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)

    return _restore


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
    shutdown_state: dict[str, Any] = {
        "requested": False,
        "reason": None,
        "requested_at_monotonic": None,
        "forced": False,
    }
    restore_signal_handlers = _install_shutdown_signal_handlers(
        runtime=runtime,
        shutdown_state=shutdown_state,
    )
    last_cleanup_date: str | None = None
    try:
        while True:
            if _maybe_force_shutdown(runtime=runtime, shutdown_state=shutdown_state):
                return 0
            if shutdown_state["requested"]:
                return 0
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
                if _maybe_force_shutdown(runtime=runtime, shutdown_state=shutdown_state):
                    return 0
                if shutdown_state["requested"]:
                    return 0
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

                if _maybe_force_shutdown(runtime=runtime, shutdown_state=shutdown_state):
                    return 0
                if shutdown_state["requested"]:
                    return 0
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
        _request_shutdown(
            runtime=runtime,
            shutdown_state=shutdown_state,
            reason="keyboard_interrupt",
        )
        return 0
    except Exception as exc:  # pragma: no cover
        runtime.logger.critical(
            log_event(events.SHUTDOWN_UNEXPECTED_ERROR, error=redact_sensitive_text(exc)),
            exc_info=True,
        )
        return 1
    finally:
        restore_signal_handlers()
        close_runtime_resources(runtime)
        _log_shutdown_complete(runtime=runtime, shutdown_state=shutdown_state)
