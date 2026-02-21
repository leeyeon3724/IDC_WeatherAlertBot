from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import cli as entrypoint
from app.settings import Settings
from app.usecases.process_cycle import CycleStats


@dataclass
class ServiceRuntimeProbe:
    cleanup_calls: list[tuple[int, bool, bool]] = field(default_factory=list)
    notifier_messages: list[str] = field(default_factory=list)
    processor_lookback_calls: list[int | None] = field(default_factory=list)
    sqlite_repo_file: Path | None = None


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "service_api_key": "test-key",
        "service_hook_url": "https://hook.example",
        "weather_alert_data_api_url": "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd",
        "sent_messages_file": tmp_path / "state.json",
        "state_repository_type": "sqlite",
        "sqlite_state_file": tmp_path / "state.db",
        "area_codes": ["L1070100"],
        "area_code_mapping": {"L1070100": "대구"},
        "request_timeout_sec": 1,
        "request_connect_timeout_sec": 1,
        "request_read_timeout_sec": 1,
        "max_retries": 1,
        "retry_delay_sec": 0,
        "notifier_timeout_sec": 1,
        "notifier_connect_timeout_sec": 1,
        "notifier_read_timeout_sec": 1,
        "notifier_max_retries": 1,
        "notifier_retry_delay_sec": 0,
        "area_max_workers": 1,
        "lookback_days": 0,
        "cycle_interval_sec": 0,
        "area_interval_sec": 0,
        "cleanup_enabled": True,
        "cleanup_retention_days": 30,
        "cleanup_include_unsent": False,
        "health_alert_enabled": True,
        "health_outage_window_sec": 600,
        "health_outage_fail_ratio_threshold": 0.7,
        "health_outage_min_failed_cycles": 6,
        "health_outage_consecutive_failures": 4,
        "health_recovery_window_sec": 900,
        "health_recovery_max_fail_ratio": 0.1,
        "health_recovery_consecutive_successes": 8,
        "health_heartbeat_interval_sec": 3600,
        "health_backoff_max_sec": 900,
        "health_recovery_backfill_max_days": 3,
        "health_recovery_backfill_window_days": 1,
        "health_recovery_backfill_max_windows_per_cycle": 3,
        "health_state_file": tmp_path / "health_state.json",
        "bot_name": "테스트봇",
        "timezone": "Asia/Seoul",
        "log_level": "INFO",
        "dry_run": False,
        "run_once": True,
    }
    base.update(overrides)
    return Settings(**base)


def patch_service_runtime(
    *,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    logger_name: str,
    cycle_stats: CycleStats,
    health_decision: ApiHealthDecision,
    fixed_now: datetime | None = None,
) -> ServiceRuntimeProbe:
    probe = ServiceRuntimeProbe()
    now = fixed_now or datetime(2026, 2, 21, 10, 0, tzinfo=UTC)

    class FakeDateTime:
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> datetime:
            if tz is None:
                return now
            return now.astimezone(tz)

    class FakeStateRepo:
        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            self.file_path = file_path
            self.logger = logger
            self.total_count = 0
            self.pending_count = 0

        def cleanup_stale(self, days: int, include_unsent: bool, dry_run: bool = False) -> int:
            probe.cleanup_calls.append((days, include_unsent, dry_run))
            return 0

    class FakeSqliteRepo(FakeStateRepo):
        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            super().__init__(file_path=file_path, logger=logger)
            probe.sqlite_repo_file = file_path

    class FakeHealthStateRepo:
        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            self.file_path = file_path
            self.logger = logger

    class FakeWeatherClient:
        def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
            self.settings = settings
            self.logger = logger

    class FakeNotifier:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def send(self, message: str, report_url: str | None = None) -> None:
            probe.notifier_messages.append(message)

    class FakeProcessor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run_once(self, lookback_days_override: int | None = None) -> CycleStats:
            probe.processor_lookback_calls.append(lookback_days_override)
            return cycle_stats

    class FakeHealthMonitor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def observe_cycle(self, **kwargs: object) -> ApiHealthDecision:
            return health_decision

        def suggested_cycle_interval_sec(self, base_interval_sec: int) -> int:
            return base_interval_sec

    logger = logging.getLogger(logger_name)
    monkeypatch.setattr(entrypoint, "setup_logging", lambda *args, **kwargs: logger)
    monkeypatch.setattr(entrypoint, "datetime", FakeDateTime)
    monkeypatch.setattr(entrypoint, "JsonStateRepository", FakeStateRepo)
    monkeypatch.setattr(entrypoint, "SqliteStateRepository", FakeSqliteRepo)
    monkeypatch.setattr(entrypoint, "JsonHealthStateRepository", FakeHealthStateRepo)
    monkeypatch.setattr(entrypoint, "ApiHealthMonitor", FakeHealthMonitor)
    monkeypatch.setattr(entrypoint, "WeatherAlertClient", FakeWeatherClient)
    monkeypatch.setattr(entrypoint, "DoorayNotifier", FakeNotifier)
    monkeypatch.setattr(entrypoint, "ProcessCycleUseCase", FakeProcessor)
    monkeypatch.setattr(
        entrypoint.Settings,
        "from_env",
        classmethod(lambda cls, env_file=".env": settings),
    )
    return probe
