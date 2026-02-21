from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import service_loop
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

    def send(self, message: str) -> None:
        if self.should_fail:
            raise NotificationError("failed", attempts=2, last_error=RuntimeError("boom"))
        self.messages.append(message)


class _FakeProcessor:
    def __init__(self, stats: CycleStats, *, raises: Exception | None = None) -> None:
        self.stats = stats
        self.raises = raises
        self.calls = 0

    def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.stats


class _FakeHealthMonitor:
    def __init__(self, decision: ApiHealthDecision, *, suggested_sec: int = 0) -> None:
        self.decision = decision
        self.suggested_sec = suggested_sec

    def observe_cycle(self, **kwargs: object) -> ApiHealthDecision:
        return self.decision

    def suggested_cycle_interval_sec(self, base_interval_sec: int) -> int:
        return self.suggested_sec


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
    monkeypatch.setattr(service_loop, "build_health_notification_message", lambda _: "msg")
    service_loop.maybe_send_health_notification(runtime=runtime_fail, health_decision=decision)


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
    service_loop.maybe_run_recovery_backfill(runtime=runtime_skip, health_decision=recovered)
    assert runtime_skip.processor.calls == 0

    runtime_fail = _runtime(
        tmp_path,
        settings_overrides={"lookback_days": 0, "health_recovery_backfill_max_days": 3},
        decision=recovered,
        processor_raises=RuntimeError("backfill error"),
    )
    service_loop.maybe_run_recovery_backfill(runtime=runtime_fail, health_decision=recovered)
    assert runtime_fail.processor.calls == 1


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


def test_run_loop_handles_keyboard_interrupt_from_processor(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, processor_raises=KeyboardInterrupt())

    result = service_loop.run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda tz: "2026-02-21",
    )

    assert result == 0


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
