from __future__ import annotations

import json
import logging
import signal
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import backfill, service_loop
from app.entrypoints.runtime_builder import ServiceRuntime
from app.observability import events
from app.services.notifier import NotificationError
from app.usecases.process_cycle import CycleStats
from tests.main_test_harness import make_settings


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class _FakeStateRepo:
    def __init__(self, removed: int = 0) -> None:
        self._removed = removed
        self.total_count = 10
        self.pending_count = 3

    def cleanup_stale(self, days: int, include_unsent: bool) -> int:
        return self._removed


class _FakeNotifier:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.messages: list[str] = []
        self.closed = False

    def send(self, message: str) -> None:
        if self.should_fail:
            raise NotificationError("failed", attempts=2, last_error=RuntimeError("boom"))
        self.messages.append(message)

    def close(self) -> None:
        self.closed = True


class _FakeProcessor:
    def __init__(self, stats: CycleStats, *, raises: Exception | None = None) -> None:
        self.stats = stats
        self.raises = raises
        self.calls = 0
        self.closed = False

    def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.stats

    def close(self) -> None:
        self.closed = True


class _FakeHealthMonitor:
    def __init__(self, decision: ApiHealthDecision, *, suggested_sec: int = 0) -> None:
        self.decision = decision
        self.suggested_sec = suggested_sec
        self._recovery_backfill_window: tuple[str, str] | None = None

    def observe_cycle(self, **kwargs: object) -> ApiHealthDecision:
        return self.decision

    def suggested_cycle_interval_sec(self, base_interval_sec: int) -> int:
        return self.suggested_sec

    def get_recovery_backfill_window(self) -> tuple[str, str] | None:
        return self._recovery_backfill_window

    def set_recovery_backfill_window(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> None:
        if start_date is None or end_date is None or start_date >= end_date:
            self._recovery_backfill_window = None
            return
        self._recovery_backfill_window = (start_date, end_date)


def _runtime(
    tmp_path: Path,
    *,
    settings_overrides: dict[str, object] | None = None,
    decision: ApiHealthDecision | None = None,
    suggested_sec: int = 0,
    processor_raises: Exception | None = None,
    notifier_should_fail: bool = False,
    cleanup_removed: int = 0,
) -> ServiceRuntime:
    settings = make_settings(tmp_path, **(settings_overrides or {}))
    logger = logging.getLogger("test.service_loop")
    logger.handlers = []
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False

    stats = CycleStats(start_date="20260220", end_date="20260221", area_count=1)
    processor = _FakeProcessor(stats, raises=processor_raises)
    return ServiceRuntime(
        settings=settings,
        logger=logger,
        state_repo=_FakeStateRepo(removed=cleanup_removed),
        notifier=_FakeNotifier(should_fail=notifier_should_fail),
        processor=processor,
        health_monitor=_FakeHealthMonitor(
            decision or ApiHealthDecision(incident_open=False),
            suggested_sec=suggested_sec,
        ),
    )


def test_maybe_auto_cleanup_skips_when_disabled_or_same_date(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, settings_overrides={"cleanup_enabled": False})

    skipped = service_loop.maybe_auto_cleanup(
        runtime=runtime,
        last_cleanup_date="2026-02-20",
        current_date="2026-02-20",
    )
    assert skipped == "2026-02-20"

    runtime_enabled = _runtime(tmp_path, settings_overrides={"cleanup_enabled": True})
    skipped_same_day = service_loop.maybe_auto_cleanup(
        runtime=runtime_enabled,
        last_cleanup_date="2026-02-20",
        current_date="2026-02-20",
    )
    assert skipped_same_day == "2026-02-20"


def test_maybe_send_health_notification_handles_empty_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = ApiHealthDecision(
        incident_open=True,
        event="outage_detected",
        should_notify=True,
    )
    runtime = _runtime(tmp_path, decision=decision)

    monkeypatch.setattr(service_loop, "build_health_notification_message", lambda _: "")
    service_loop.maybe_send_health_notification(runtime=runtime, health_decision=decision)
    assert runtime.notifier.messages == []

    runtime_fail = _runtime(tmp_path, decision=decision, notifier_should_fail=True)
    failure_handler = _CaptureHandler()
    runtime_fail.logger.handlers = [failure_handler]
    runtime_fail.logger.setLevel(logging.INFO)
    runtime_fail.logger.propagate = False
    monkeypatch.setattr(service_loop, "build_health_notification_message", lambda _: "msg")
    service_loop.maybe_send_health_notification(runtime=runtime_fail, health_decision=decision)

    payloads = [json.loads(message) for message in failure_handler.messages]
    failure_events = [
        payload for payload in payloads if payload.get("event") == events.HEALTH_NOTIFICATION_FAILED
    ]
    assert len(failure_events) == 1
    assert failure_events[0]["health_event"] == "outage_detected"
    assert failure_events[0]["attempts"] == 2
    assert "boom" in str(failure_events[0]["error"])


def test_maybe_run_recovery_backfill_branches(tmp_path: Path) -> None:
    recovered = ApiHealthDecision(
        incident_open=False,
        event="recovered",
        should_notify=False,
        incident_duration_sec=2 * 86400,
    )

    runtime_skip = _runtime(
        tmp_path,
        settings_overrides={"lookback_days": 2, "health_recovery_backfill_max_days": 3},
        decision=recovered,
    )
    backfill.maybe_run_recovery_backfill(runtime=runtime_skip, health_decision=recovered)
    assert runtime_skip.processor.calls == 0

    runtime_fail = _runtime(
        tmp_path,
        settings_overrides={"lookback_days": 0, "health_recovery_backfill_max_days": 3},
        decision=recovered,
        processor_raises=RuntimeError("backfill error"),
    )
    failure_handler = _CaptureHandler()
    runtime_fail.logger.handlers = [failure_handler]
    runtime_fail.logger.setLevel(logging.INFO)
    runtime_fail.logger.propagate = False
    backfill.maybe_run_recovery_backfill(runtime=runtime_fail, health_decision=recovered)
    assert runtime_fail.processor.calls == 1

    payloads = [json.loads(message) for message in failure_handler.messages]
    start_events = [
        payload for payload in payloads if payload.get("event") == events.HEALTH_BACKFILL_START
    ]
    failed_events = [
        payload for payload in payloads if payload.get("event") == events.HEALTH_BACKFILL_FAILED
    ]
    assert len(start_events) == 1
    assert len(failed_events) == 1
    assert failed_events[0]["lookback_days"] == 2
    assert failed_events[0]["backfill_extra_days"] == 2
    assert failed_events[0]["processed_days"] == 0
    assert failed_events[0]["processed_windows"] == 0
    assert "backfill error" in str(failed_events[0]["error"])


def test_maybe_run_recovery_backfill_splits_windows_with_budget(
    tmp_path: Path,
) -> None:
    recovered = ApiHealthDecision(
        incident_open=False,
        event="recovered",
        should_notify=False,
        incident_duration_sec=7 * 86400,
    )
    runtime = _runtime(
        tmp_path,
        settings_overrides={
            "lookback_days": 0,
            "health_recovery_backfill_max_days": 5,
            "health_recovery_backfill_window_days": 2,
            "health_recovery_backfill_max_windows_per_cycle": 2,
        },
        decision=recovered,
    )
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False

    class _RangeProcessor:
        def __init__(self, stats: CycleStats) -> None:
            self.stats = stats
            self.range_calls: list[tuple[str, str]] = []

        def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
            raise AssertionError("run_once should not be called when run_date_range is available")

        def run_date_range(self, *, start_date: str, end_date: str) -> CycleStats:
            self.range_calls.append((start_date, end_date))
            return self.stats

    processor = _RangeProcessor(runtime.processor.stats)
    object.__setattr__(runtime, "processor", processor)

    backfill.maybe_run_recovery_backfill(
        runtime=runtime,
        health_decision=recovered,
        now_local_date_fn=lambda timezone: date(2026, 2, 21),
    )

    assert processor.range_calls == [("20260216", "20260218"), ("20260218", "20260220")]
    payloads = [json.loads(message) for message in handler.messages]
    complete_payloads = [
        payload for payload in payloads if payload.get("event") == events.HEALTH_BACKFILL_COMPLETE
    ]
    assert len(complete_payloads) == 1
    assert complete_payloads[0]["processed_days"] == 4
    assert complete_payloads[0]["remaining_days"] == 1
    assert complete_payloads[0]["processed_windows"] == 2


def test_maybe_run_recovery_backfill_resumes_pending_window_next_calls(
    tmp_path: Path,
) -> None:
    recovered = ApiHealthDecision(
        incident_open=False,
        event="recovered",
        should_notify=False,
        incident_duration_sec=7 * 86400,
    )
    stable = ApiHealthDecision(
        incident_open=False,
        event=None,
        should_notify=False,
    )
    runtime = _runtime(
        tmp_path,
        settings_overrides={
            "lookback_days": 0,
            "health_recovery_backfill_max_days": 5,
            "health_recovery_backfill_window_days": 2,
            "health_recovery_backfill_max_windows_per_cycle": 1,
        },
        decision=recovered,
    )

    class _RangeProcessor:
        def __init__(self, stats: CycleStats) -> None:
            self.stats = stats
            self.range_calls: list[tuple[str, str]] = []

        def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
            raise AssertionError("run_once should not be called when run_date_range is available")

        def run_date_range(self, *, start_date: str, end_date: str) -> CycleStats:
            self.range_calls.append((start_date, end_date))
            return self.stats

    processor = _RangeProcessor(runtime.processor.stats)
    object.__setattr__(runtime, "processor", processor)

    def now_local_date(timezone: str) -> date:
        return date(2026, 2, 21)

    backfill.maybe_run_recovery_backfill(
        runtime=runtime,
        health_decision=recovered,
        now_local_date_fn=now_local_date,
    )
    assert processor.range_calls == [("20260216", "20260218")]
    assert runtime.health_monitor.get_recovery_backfill_window() == ("20260218", "20260221")

    backfill.maybe_run_recovery_backfill(
        runtime=runtime,
        health_decision=stable,
        now_local_date_fn=now_local_date,
    )
    assert processor.range_calls == [("20260216", "20260218"), ("20260218", "20260220")]
    assert runtime.health_monitor.get_recovery_backfill_window() == ("20260220", "20260221")

    backfill.maybe_run_recovery_backfill(
        runtime=runtime,
        health_decision=stable,
        now_local_date_fn=now_local_date,
    )
    assert processor.range_calls == [
        ("20260216", "20260218"),
        ("20260218", "20260220"),
        ("20260220", "20260221"),
    ]
    assert runtime.health_monitor.get_recovery_backfill_window() is None


def test_sleep_until_next_cycle_calls_sleep_when_adjusted(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, settings_overrides={"cycle_interval_sec": 10}, suggested_sec=30)
    decision = ApiHealthDecision(incident_open=True)
    sleep_calls: list[float] = []

    service_loop.sleep_until_next_cycle(
        runtime=runtime,
        health_decision=decision,
        sleep_fn=lambda value: sleep_calls.append(value),
    )

    assert sleep_calls == [30.0]


def test_install_shutdown_signal_handlers_marks_state_and_restores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False
    shutdown_state: dict[str, object] = {
        "requested": False,
        "reason": None,
        "requested_at_monotonic": None,
        "forced": False,
    }

    previous_handlers: dict[signal.Signals, object] = {}
    assigned_handlers: dict[signal.Signals, list[object]] = {}

    def _fake_getsignal(sig: signal.Signals) -> object:
        previous = object()
        previous_handlers[sig] = previous
        return previous

    def _fake_signal(sig: signal.Signals, assigned: object) -> None:
        assigned_handlers.setdefault(sig, []).append(assigned)

    monkeypatch.setattr(service_loop.signal, "getsignal", _fake_getsignal)
    monkeypatch.setattr(service_loop.signal, "signal", _fake_signal)

    restore = service_loop._install_shutdown_signal_handlers(
        runtime=runtime,
        shutdown_state=shutdown_state,
    )
    sigterm_handler = assigned_handlers[signal.SIGTERM][0]
    assert callable(sigterm_handler)

    sigterm_handler(signal.SIGTERM, None)  # type: ignore[misc]

    assert shutdown_state["requested"] is True
    assert shutdown_state["reason"] == "sigterm"
    payloads = [json.loads(message) for message in handler.messages]
    assert sum(payload.get("event") == events.SHUTDOWN_INTERRUPT for payload in payloads) == 1
    assert sum(payload.get("event") == events.SHUTDOWN_START for payload in payloads) == 1

    restore()
    assert assigned_handlers[signal.SIGTERM][-1] is previous_handlers[signal.SIGTERM]
    assert assigned_handlers[signal.SIGINT][-1] is previous_handlers[signal.SIGINT]


def test_run_loop_handles_keyboard_interrupt_from_processor(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, processor_raises=KeyboardInterrupt())

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
    )

    assert result == 0
    assert runtime.processor.closed is True
    assert runtime.notifier.closed is True


def test_run_loop_gracefully_stops_when_shutdown_state_is_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": False, "cycle_interval_sec": 10},
        suggested_sec=10,
    )
    state_ref: dict[str, dict[str, object]] = {}

    def _fake_install(
        *,
        runtime: ServiceRuntime,
        shutdown_state: dict[str, object],
    ):
        state_ref["value"] = shutdown_state
        return lambda: None

    monkeypatch.setattr(service_loop, "_install_shutdown_signal_handlers", _fake_install)
    sleep_calls: list[float] = []

    def _sleep_and_request_shutdown(seconds: float) -> None:
        sleep_calls.append(seconds)
        state_ref["value"]["requested"] = True

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
        sleep_fn=_sleep_and_request_shutdown,
    )

    assert result == 0
    assert sleep_calls == [10.0]
    assert runtime.processor.calls == 1
    assert runtime.processor.closed is True
    assert runtime.notifier.closed is True


def test_request_shutdown_logs_start_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime(tmp_path, settings_overrides={"shutdown_timeout_sec": 12})
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False
    monkeypatch.setattr(service_loop.time, "monotonic", lambda: 100.0)
    shutdown_state: dict[str, object] = {
        "requested": False,
        "reason": None,
        "requested_at_monotonic": None,
        "forced": False,
    }

    service_loop._request_shutdown(
        runtime=runtime,
        shutdown_state=shutdown_state,
        reason="sigterm",
    )

    assert shutdown_state["requested"] is True
    assert shutdown_state["reason"] == "sigterm"
    assert shutdown_state["requested_at_monotonic"] == 100.0
    payloads = [json.loads(message) for message in handler.messages]
    assert sum(payload.get("event") == events.SHUTDOWN_START for payload in payloads) == 1


def test_maybe_force_shutdown_emits_forced_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path, settings_overrides={"shutdown_timeout_sec": 3})
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False
    monkeypatch.setattr(service_loop.time, "monotonic", lambda: 13.5)
    shutdown_state: dict[str, object] = {
        "requested": True,
        "reason": "sigterm",
        "requested_at_monotonic": 10.0,
        "forced": False,
    }

    forced = service_loop._maybe_force_shutdown(runtime=runtime, shutdown_state=shutdown_state)

    assert forced is True
    assert shutdown_state["forced"] is True
    payloads = [json.loads(message) for message in handler.messages]
    assert sum(payload.get("event") == events.SHUTDOWN_FORCED for payload in payloads) == 1


def test_run_loop_non_run_once_executes_sleep_then_interrupt(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": False, "cycle_interval_sec": 10},
        suggested_sec=10,
    )
    sleep_calls: list[float] = []

    def _sleep_and_interrupt(seconds: float) -> None:
        sleep_calls.append(seconds)
        raise KeyboardInterrupt

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
        sleep_fn=_sleep_and_interrupt,
    )

    assert result == 0
    assert sleep_calls == [10.0]


def test_run_loop_emits_shutdown_complete_event_on_interrupt(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": False, "cycle_interval_sec": 5},
        suggested_sec=5,
    )
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
        sleep_fn=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert result == 0
    payloads = [json.loads(message) for message in handler.messages]
    complete_payloads = [
        payload for payload in payloads if payload.get("event") == events.SHUTDOWN_COMPLETE
    ]
    assert len(complete_payloads) == 1
    assert complete_payloads[0]["reason"] == "keyboard_interrupt"
    assert complete_payloads[0]["forced"] is False


def test_run_loop_non_fatal_exception_continues_next_iteration(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": False, "cycle_interval_sec": 7},
        suggested_sec=7,
    )
    stats = runtime.processor.stats

    class _FlakyProcessor:
        def __init__(self, cycle_stats: CycleStats) -> None:
            self.calls = 0
            self._cycle_stats = cycle_stats

        def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return self._cycle_stats

    object.__setattr__(runtime, "processor", _FlakyProcessor(stats))
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False
    sleep_calls: list[float] = []

    def _sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            raise KeyboardInterrupt

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
        sleep_fn=_sleep,
    )

    assert result == 0
    assert sleep_calls == [7.0, 7.0]
    payloads = [json.loads(message) for message in handler.messages]
    assert sum(p.get("event") == events.CYCLE_ITERATION_FAILED for p in payloads) == 1
    assert sum(p.get("event") == events.CYCLE_COMPLETE for p in payloads) == 1


def test_run_loop_non_fatal_exception_uses_min_backoff_when_interval_zero(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": False, "cycle_interval_sec": 0},
        suggested_sec=0,
    )

    class _AlwaysFailingProcessor:
        def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
            raise RuntimeError("temporary failure")

    object.__setattr__(runtime, "processor", _AlwaysFailingProcessor())
    sleep_calls: list[float] = []

    def _sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        raise KeyboardInterrupt

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
        sleep_fn=_sleep,
    )

    assert result == 0
    assert sleep_calls == [1.0]


def test_run_loop_exits_on_fatal_cycle_exception(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": False, "cycle_interval_sec": 7},
        processor_raises=MemoryError("out-of-memory"),
    )
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False
    sleep_calls: list[float] = []

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    assert result == 1
    assert runtime.processor.closed is True
    assert runtime.notifier.closed is True
    assert sleep_calls == []
    payloads = [json.loads(message) for message in handler.messages]
    assert sum(p.get("event") == events.CYCLE_FATAL_ERROR for p in payloads) == 1
    assert sum(p.get("event") == events.CYCLE_ITERATION_FAILED for p in payloads) == 0


def test_run_loop_run_once_exception_exits_as_fatal(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        settings_overrides={"run_once": True},
        processor_raises=RuntimeError("single-run failure"),
    )
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
    )

    assert result == 1
    assert runtime.processor.closed is True
    assert runtime.notifier.closed is True
    payloads = [json.loads(message) for message in handler.messages]
    assert sum(p.get("event") == events.CYCLE_FATAL_ERROR for p in payloads) == 1


def test_run_loop_run_once_success_closes_resources(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, settings_overrides={"run_once": True})

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
    )

    assert result == 0
    assert runtime.processor.closed is True
    assert runtime.notifier.closed is True


def test_run_loop_emits_cycle_cost_metrics_event(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.processor.stats = CycleStats(
        start_date="20260220",
        end_date="20260221",
        area_count=2,
        areas_processed=2,
        alerts_fetched=3,
        api_fetch_calls=2,
        notification_attempts=2,
        sent_count=1,
        send_failures=1,
        notification_dry_run_skips=0,
        pending_total=1,
    )
    handler = _CaptureHandler()
    runtime.logger.handlers = [handler]
    runtime.logger.setLevel(logging.INFO)
    runtime.logger.propagate = False

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
    )

    assert result == 0
    payloads = [json.loads(message) for message in handler.messages]
    cycle_cost = [
        payload for payload in payloads if payload.get("event") == events.CYCLE_COST_METRICS
    ]
    assert len(cycle_cost) == 1
    assert cycle_cost[0]["api_fetch_calls"] == 2
    assert cycle_cost[0]["notification_attempts"] == 2
    assert cycle_cost[0]["notification_sent"] == 1
    assert cycle_cost[0]["notification_failures"] == 1
    assert cycle_cost[0]["notification_backpressure_skips"] == 0
