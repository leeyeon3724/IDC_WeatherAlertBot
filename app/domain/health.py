from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(value: datetime) -> str:
    normalized = value.astimezone(UTC).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def parse_utc_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class HealthCycleSample:
    recorded_at: datetime
    total_areas: int
    failed_areas: int
    error_counts: dict[str, int] = field(default_factory=dict)
    last_error: str | None = None

    @property
    def fail_ratio(self) -> float:
        if self.total_areas <= 0:
            return 0.0
        return self.failed_areas / self.total_areas

    def to_dict(self) -> dict[str, object]:
        return {
            "recorded_at": to_utc_iso(self.recorded_at),
            "total_areas": self.total_areas,
            "failed_areas": self.failed_areas,
            "error_counts": dict(self.error_counts),
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, raw: object) -> HealthCycleSample | None:
        if not isinstance(raw, dict):
            return None
        recorded_at = parse_utc_iso(raw.get("recorded_at"))
        if recorded_at is None:
            return None
        total_areas = raw.get("total_areas")
        failed_areas = raw.get("failed_areas")
        if not isinstance(total_areas, int) or not isinstance(failed_areas, int):
            return None
        error_counts: dict[str, int] = {}
        raw_counts = raw.get("error_counts")
        if isinstance(raw_counts, dict):
            for key, value in raw_counts.items():
                if isinstance(key, str) and isinstance(value, int) and value >= 0:
                    error_counts[key] = value
        last_error = raw.get("last_error")
        return cls(
            recorded_at=recorded_at,
            total_areas=max(total_areas, 0),
            failed_areas=max(failed_areas, 0),
            error_counts=error_counts,
            last_error=last_error if isinstance(last_error, str) and last_error else None,
        )


@dataclass(frozen=True)
class HealthPolicy:
    outage_window_sec: int = 600
    outage_fail_ratio_threshold: float = 0.7
    outage_min_failed_cycles: int = 6
    outage_consecutive_failures: int = 4
    recovery_window_sec: int = 900
    recovery_max_fail_ratio: float = 0.1
    recovery_consecutive_successes: int = 8
    heartbeat_interval_sec: int = 3600
    max_backoff_sec: int = 900

    def max_window_sec(self) -> int:
        return max(self.outage_window_sec, self.recovery_window_sec)


@dataclass
class ApiHealthState:
    incident_open: bool = False
    incident_started_at: datetime | None = None
    incident_notified_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_recovered_at: datetime | None = None
    consecutive_severe_failures: int = 0
    consecutive_stable_successes: int = 0
    incident_total_cycles: int = 0
    incident_failed_cycles: int = 0
    incident_error_counts: dict[str, int] = field(default_factory=dict)
    recovery_backfill_pending_start_date: str | None = None
    recovery_backfill_pending_end_date: str | None = None
    recent_cycles: list[HealthCycleSample] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "incident_open": self.incident_open,
            "incident_started_at": (
                to_utc_iso(self.incident_started_at) if self.incident_started_at else None
            ),
            "incident_notified_at": (
                to_utc_iso(self.incident_notified_at) if self.incident_notified_at else None
            ),
            "last_heartbeat_at": (
                to_utc_iso(self.last_heartbeat_at) if self.last_heartbeat_at else None
            ),
            "last_recovered_at": (
                to_utc_iso(self.last_recovered_at) if self.last_recovered_at else None
            ),
            "consecutive_severe_failures": self.consecutive_severe_failures,
            "consecutive_stable_successes": self.consecutive_stable_successes,
            "incident_total_cycles": self.incident_total_cycles,
            "incident_failed_cycles": self.incident_failed_cycles,
            "incident_error_counts": dict(self.incident_error_counts),
            "recovery_backfill_pending_start_date": self.recovery_backfill_pending_start_date,
            "recovery_backfill_pending_end_date": self.recovery_backfill_pending_end_date,
            "recent_cycles": [cycle.to_dict() for cycle in self.recent_cycles],
        }

    @classmethod
    def from_dict(cls, raw: object) -> ApiHealthState:
        if not isinstance(raw, dict):
            return cls()

        state = cls(
            incident_open=bool(raw.get("incident_open", False)),
            incident_started_at=parse_utc_iso(raw.get("incident_started_at")),
            incident_notified_at=parse_utc_iso(raw.get("incident_notified_at")),
            last_heartbeat_at=parse_utc_iso(raw.get("last_heartbeat_at")),
            last_recovered_at=parse_utc_iso(raw.get("last_recovered_at")),
            consecutive_severe_failures=_non_negative_int(raw.get("consecutive_severe_failures")),
            consecutive_stable_successes=_non_negative_int(raw.get("consecutive_stable_successes")),
            incident_total_cycles=_non_negative_int(raw.get("incident_total_cycles")),
            incident_failed_cycles=_non_negative_int(raw.get("incident_failed_cycles")),
            incident_error_counts=_normalize_error_counts(raw.get("incident_error_counts")),
            recovery_backfill_pending_start_date=_normalize_compact_date(
                raw.get("recovery_backfill_pending_start_date")
            ),
            recovery_backfill_pending_end_date=_normalize_compact_date(
                raw.get("recovery_backfill_pending_end_date")
            ),
        )

        raw_cycles = raw.get("recent_cycles")
        if isinstance(raw_cycles, list):
            for item in raw_cycles:
                sample = HealthCycleSample.from_dict(item)
                if sample is not None:
                    state.recent_cycles.append(sample)

        return state

    def append_cycle(self, sample: HealthCycleSample) -> None:
        self.recent_cycles.append(sample)

    def trim_recent_cycles(self, *, now: datetime, retention_sec: int) -> None:
        if retention_sec <= 0:
            self.recent_cycles = []
            return
        threshold = now - timedelta(seconds=retention_sec)
        self.recent_cycles = [
            sample for sample in self.recent_cycles if sample.recorded_at >= threshold
        ]

    def cycles_in_window(self, *, now: datetime, window_sec: int) -> list[HealthCycleSample]:
        if window_sec <= 0:
            return []
        threshold = now - timedelta(seconds=window_sec)
        return [sample for sample in self.recent_cycles if sample.recorded_at >= threshold]


@dataclass(frozen=True)
class ApiHealthDecision:
    incident_open: bool
    event: str | None = None
    should_notify: bool = False
    outage_window_cycles: int = 0
    outage_window_failed_cycles: int = 0
    outage_window_fail_ratio: float = 0.0
    recovery_window_cycles: int = 0
    recovery_window_fail_ratio: float = 0.0
    consecutive_severe_failures: int = 0
    consecutive_stable_successes: int = 0
    incident_duration_sec: int = 0
    incident_total_cycles: int = 0
    incident_failed_cycles: int = 0
    incident_error_counts: dict[str, int] = field(default_factory=dict)
    representative_error: str | None = None


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int):
        return 0
    return max(value, 0)


def _normalize_error_counts(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, int) and value >= 0:
            normalized[key] = value
    return normalized


def _normalize_compact_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return text
