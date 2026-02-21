from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import backfill, service_loop
from app.entrypoints.runtime_builder import ServiceRuntime
from app.entrypoints.service_loop import run_loop
from app.repositories.health_state_repo import JsonHealthStateRepository
from app.usecases.health_monitor import ApiHealthMonitor
from app.usecases.process_cycle import CycleStats
from tests.main_test_harness import make_settings


@dataclass
class _Processor:
    cycle_stats: CycleStats
    calls: list[int | None]

    def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
        self.calls.append(lookback_days_override)
        return self.cycle_stats


class _StateRepo:
    total_count = 0
    pending_count = 0

    def cleanup_stale(self, days: int, include_unsent: bool) -> int:
        return 0


class _Notifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


class _HealthMonitor:
    def __init__(self, decisions: list[ApiHealthDecision], suggested_sec: int = 1) -> None:
        self._decisions = decisions
        self._index = 0
        self._suggested_sec = suggested_sec

    def observe_cycle(self, **kwargs: object) -> ApiHealthDecision:
        decision = self._decisions[self._index]
        if self._index < len(self._decisions) - 1:
            self._index += 1
        return decision

    def suggested_cycle_interval_sec(self, base_interval_sec: int) -> int:
        return self._suggested_sec


def test_run_loop_end_to_end_outage_heartbeat_recovered_backfill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decisions = [
        ApiHealthDecision(incident_open=True, event="outage_detected", should_notify=True),
        ApiHealthDecision(incident_open=True, event="outage_heartbeat", should_notify=True),
        ApiHealthDecision(
            incident_open=False,
            event="recovered",
            should_notify=False,
            incident_duration_sec=90000,
        ),
    ]
    health_monitor = _HealthMonitor(decisions=decisions, suggested_sec=1)
    processor_calls: list[int | None] = []
    processor = _Processor(
        cycle_stats=CycleStats(start_date="20260220", end_date="20260221", area_count=1),
        calls=processor_calls,
    )
    notifier = _Notifier()

    settings = make_settings(
        tmp_path,
        run_once=False,
        cycle_interval_sec=1,
        cleanup_enabled=False,
        lookback_days=0,
        health_recovery_backfill_max_days=3,
    )
    logger = logging.getLogger("test.service_loop.integration")
    logger.handlers = []
    logger.addHandler(logging.NullHandler())
    logger.propagate = False

    runtime = ServiceRuntime(
        settings=settings,
        logger=logger,
        state_repo=_StateRepo(),
        notifier=notifier,
        processor=processor,
        health_monitor=health_monitor,
    )

    monkeypatch.setattr(
        "app.entrypoints.service_loop.build_health_notification_message",
        lambda decision: f"health:{decision.event}",
    )

    sleep_counter = {"count": 0}

    def _sleep_and_stop(seconds: float) -> None:
        sleep_counter["count"] += 1
        if sleep_counter["count"] >= 3:
            raise KeyboardInterrupt

    result = run_loop(
        runtime,
        now_utc_fn=lambda: datetime(2026, 2, 21, tzinfo=UTC),
        now_local_date_fn=lambda _: "2026-02-21",
        sleep_fn=_sleep_and_stop,
    )

    assert result == 0
    assert notifier.messages == ["health:outage_detected", "health:outage_heartbeat"]
    assert processor_calls == [None, None, None, 2]


def test_recovery_backfill_resumes_after_runtime_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RangeProcessor:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []
            self.stats = CycleStats(start_date="20260220", end_date="20260221", area_count=1)

        def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
            raise AssertionError("run_once should not be used when run_date_range exists")

        def run_date_range(self, *, start_date: str, end_date: str) -> CycleStats:
            self.calls.append((start_date, end_date))
            return self.stats

    class _FixedDateTime:
        @classmethod
        def now(cls, tz: object | None = None) -> datetime:
            fixed = datetime(2026, 2, 21, 10, 0, tzinfo=UTC)
            if tz is None:
                return fixed
            return fixed.astimezone(tz)  # type: ignore[arg-type]

    monkeypatch.setattr(backfill, "datetime", _FixedDateTime)

    settings = make_settings(
        tmp_path,
        run_once=True,
        lookback_days=0,
        health_recovery_backfill_max_days=5,
        health_recovery_backfill_window_days=2,
        health_recovery_backfill_max_windows_per_cycle=1,
        health_state_file=tmp_path / "health_state.json",
    )
    logger = logging.getLogger("test.service_loop.integration.resume")
    logger.handlers = []
    logger.addHandler(logging.NullHandler())
    logger.propagate = False

    runtime_first = ServiceRuntime(
        settings=settings,
        logger=logger,
        state_repo=_StateRepo(),
        notifier=_Notifier(),
        processor=_RangeProcessor(),
        health_monitor=ApiHealthMonitor(
            state_repo=JsonHealthStateRepository(settings.health_state_file),
        ),
    )
    recovered = ApiHealthDecision(
        incident_open=False,
        event="recovered",
        should_notify=False,
        incident_duration_sec=7 * 86400,
    )
    backfill.maybe_run_recovery_backfill(runtime=runtime_first, health_decision=recovered)
    assert runtime_first.processor.calls == [("20260216", "20260218")]

    runtime_second = ServiceRuntime(
        settings=settings,
        logger=logger,
        state_repo=_StateRepo(),
        notifier=_Notifier(),
        processor=_RangeProcessor(),
        health_monitor=ApiHealthMonitor(
            state_repo=JsonHealthStateRepository(settings.health_state_file),
        ),
    )
    stable = ApiHealthDecision(incident_open=False, event=None, should_notify=False)
    backfill.maybe_run_recovery_backfill(runtime=runtime_second, health_decision=stable)
    assert runtime_second.processor.calls == [("20260218", "20260220")]
