from __future__ import annotations

import logging
from datetime import datetime

from app.domain.health import (
    ApiHealthDecision,
    HealthCycleSample,
    HealthPolicy,
)
from app.repositories.health_state_repository import HealthStateRepository


class ApiHealthMonitor:
    def __init__(
        self,
        state_repo: HealthStateRepository,
        policy: HealthPolicy | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.state_repo = state_repo
        self.policy = policy or HealthPolicy()
        self.logger = logger or logging.getLogger("weather_alert_bot.health_monitor")
        self.state = state_repo.state

    def observe_cycle(
        self,
        *,
        now: datetime,
        total_areas: int,
        failed_areas: int,
        error_counts: dict[str, int] | None = None,
        representative_error: str | None = None,
    ) -> ApiHealthDecision:
        counts = dict(error_counts or {})
        sample = HealthCycleSample(
            recorded_at=now,
            total_areas=max(total_areas, 0),
            failed_areas=max(failed_areas, 0),
            error_counts=counts,
            last_error=representative_error,
        )

        self.state.append_cycle(sample)
        self.state.trim_recent_cycles(
            now=now,
            retention_sec=self.policy.max_window_sec() + self.policy.heartbeat_interval_sec,
        )
        self._update_consecutive_counters(sample)

        if self.state.incident_open:
            self.state.incident_total_cycles += 1
            if sample.failed_areas > 0:
                self.state.incident_failed_cycles += 1
                for code, value in counts.items():
                    self.state.incident_error_counts[code] = (
                        self.state.incident_error_counts.get(code, 0) + max(value, 0)
                    )

        outage_window = self.state.cycles_in_window(
            now=now,
            window_sec=self.policy.outage_window_sec,
        )
        recovery_window = self.state.cycles_in_window(
            now=now,
            window_sec=self.policy.recovery_window_sec,
        )

        outage_window_failed = self._count_severe_failures(outage_window)
        outage_window_ratio = self._window_fail_ratio(outage_window)
        recovery_window_ratio = self._window_fail_ratio(recovery_window)

        decision = ApiHealthDecision(
            incident_open=self.state.incident_open,
            outage_window_cycles=len(outage_window),
            outage_window_failed_cycles=outage_window_failed,
            outage_window_fail_ratio=outage_window_ratio,
            recovery_window_cycles=len(recovery_window),
            recovery_window_fail_ratio=recovery_window_ratio,
            consecutive_severe_failures=self.state.consecutive_severe_failures,
            consecutive_stable_successes=self.state.consecutive_stable_successes,
            incident_duration_sec=self._incident_duration_sec(now),
            incident_total_cycles=self.state.incident_total_cycles,
            incident_failed_cycles=self.state.incident_failed_cycles,
            incident_error_counts=dict(self.state.incident_error_counts),
            representative_error=representative_error,
        )

        if not self.state.incident_open and self._is_outage(outage_window, outage_window_failed):
            self._open_incident(now)
            decision = self._decision_with_event(
                decision,
                event="outage_detected",
                incident_open=True,
            )
        elif self.state.incident_open and self._is_recovered(recovery_window):
            self._close_incident(now)
            decision = self._decision_with_event(decision, event="recovered", incident_open=False)
        elif self.state.incident_open and self._should_send_heartbeat(now):
            self.state.last_heartbeat_at = now
            decision = self._decision_with_event(
                decision,
                event="outage_heartbeat",
                incident_open=True,
            )

        self.state_repo.update_state(self.state)
        return decision

    def suggested_cycle_interval_sec(self, base_interval_sec: int) -> int:
        if base_interval_sec <= 0:
            return 0
        if not self.state.incident_open:
            return base_interval_sec

        multiplier = 1
        threshold = max(1, self.policy.outage_consecutive_failures)
        if self.state.consecutive_severe_failures >= threshold * 3:
            multiplier = 8
        elif self.state.consecutive_severe_failures >= threshold * 2:
            multiplier = 4
        elif self.state.consecutive_severe_failures >= threshold:
            multiplier = 2

        suggested = base_interval_sec * multiplier
        suggested = max(base_interval_sec, suggested)
        return min(suggested, self.policy.max_backoff_sec)

    def get_recovery_backfill_window(self) -> tuple[str, str] | None:
        start_date = self.state.recovery_backfill_pending_start_date
        end_date = self.state.recovery_backfill_pending_end_date
        if not start_date or not end_date:
            return None
        if start_date >= end_date:
            return None
        return start_date, end_date

    def set_recovery_backfill_window(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> None:
        if (
            start_date is None
            or end_date is None
            or start_date >= end_date
        ):
            self.state.recovery_backfill_pending_start_date = None
            self.state.recovery_backfill_pending_end_date = None
        else:
            self.state.recovery_backfill_pending_start_date = start_date
            self.state.recovery_backfill_pending_end_date = end_date
        self.state_repo.update_state(self.state)

    def _is_outage(self, window: list[HealthCycleSample], severe_failed: int) -> bool:
        if severe_failed < self.policy.outage_min_failed_cycles:
            return False
        if self.state.consecutive_severe_failures < self.policy.outage_consecutive_failures:
            return False
        return bool(window)

    def _is_recovered(self, window: list[HealthCycleSample]) -> bool:
        if self.state.consecutive_stable_successes < self.policy.recovery_consecutive_successes:
            return False
        if len(window) < self.policy.recovery_consecutive_successes:
            return False
        return self._window_fail_ratio(window) <= self.policy.recovery_max_fail_ratio

    def _should_send_heartbeat(self, now: datetime) -> bool:
        if self.state.last_heartbeat_at is None:
            return True
        elapsed = (now - self.state.last_heartbeat_at).total_seconds()
        return elapsed >= self.policy.heartbeat_interval_sec

    def _open_incident(self, now: datetime) -> None:
        self.state.incident_open = True
        self.state.incident_started_at = now
        self.state.incident_notified_at = now
        self.state.last_heartbeat_at = now
        self.state.consecutive_stable_successes = 0
        self.state.incident_total_cycles = 0
        self.state.incident_failed_cycles = 0
        self.state.incident_error_counts = {}

    def _close_incident(self, now: datetime) -> None:
        self.state.incident_open = False
        self.state.last_recovered_at = now
        self.state.last_heartbeat_at = None
        self.state.incident_notified_at = None
        self.state.incident_started_at = None
        self.state.incident_total_cycles = 0
        self.state.incident_failed_cycles = 0
        self.state.incident_error_counts = {}
        self.state.consecutive_severe_failures = 0

    def _update_consecutive_counters(self, sample: HealthCycleSample) -> None:
        if sample.fail_ratio >= self.policy.outage_fail_ratio_threshold:
            self.state.consecutive_severe_failures += 1
            self.state.consecutive_stable_successes = 0
            return
        self.state.consecutive_severe_failures = 0
        if sample.fail_ratio <= self.policy.recovery_max_fail_ratio:
            self.state.consecutive_stable_successes += 1
        else:
            self.state.consecutive_stable_successes = 0

    def _count_severe_failures(self, window: list[HealthCycleSample]) -> int:
        return sum(
            1 for sample in window if sample.fail_ratio >= self.policy.outage_fail_ratio_threshold
        )

    @staticmethod
    def _window_fail_ratio(window: list[HealthCycleSample]) -> float:
        if not window:
            return 0.0
        total_areas = sum(sample.total_areas for sample in window)
        failed_areas = sum(sample.failed_areas for sample in window)
        if total_areas <= 0:
            return 0.0
        return failed_areas / total_areas

    def _incident_duration_sec(self, now: datetime) -> int:
        if self.state.incident_started_at is None:
            return 0
        return max(0, int((now - self.state.incident_started_at).total_seconds()))

    @staticmethod
    def _decision_with_event(
        decision: ApiHealthDecision,
        *,
        event: str,
        incident_open: bool,
    ) -> ApiHealthDecision:
        return ApiHealthDecision(
            incident_open=incident_open,
            event=event,
            should_notify=True,
            outage_window_cycles=decision.outage_window_cycles,
            outage_window_failed_cycles=decision.outage_window_failed_cycles,
            outage_window_fail_ratio=decision.outage_window_fail_ratio,
            recovery_window_cycles=decision.recovery_window_cycles,
            recovery_window_fail_ratio=decision.recovery_window_fail_ratio,
            consecutive_severe_failures=decision.consecutive_severe_failures,
            consecutive_stable_successes=decision.consecutive_stable_successes,
            incident_duration_sec=decision.incident_duration_sec,
            incident_total_cycles=decision.incident_total_cycles,
            incident_failed_cycles=decision.incident_failed_cycles,
            incident_error_counts=dict(decision.incident_error_counts),
            representative_error=decision.representative_error,
        )
