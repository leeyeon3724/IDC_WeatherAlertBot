from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import cli as entrypoint
from app.settings import Settings, SettingsError
from app.usecases.process_cycle import CycleStats


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base = {
        "service_api_key": "test-key",
        "service_hook_url": "https://hook.example",
        "weather_alert_data_api_url": "https://api.example",
        "sent_messages_file": tmp_path / "state.json",
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
        "cleanup_include_unsent": True,
        "health_alert_enabled": True,
        "health_outage_window_sec": 600,
        "health_outage_fail_ratio_threshold": 0.7,
        "health_outage_min_failed_cycles": 6,
        "health_outage_consecutive_failures": 4,
        "health_recovery_window_sec": 900,
        "health_recovery_max_fail_ratio": 0.1,
        "health_recovery_consecutive_successes": 8,
        "health_heartbeat_interval_sec": 3600,
        "health_state_file": tmp_path / "health_state.json",
        "bot_name": "테스트봇",
        "timezone": "Asia/Seoul",
        "log_level": "INFO",
        "dry_run": False,
        "run_once": True,
    }
    base.update(overrides)
    return Settings(**base)


def test_run_service_returns_1_on_invalid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("test.main.invalid")
    monkeypatch.setattr(entrypoint, "setup_logging", lambda *args, **kwargs: logger)

    def _raise_settings(cls, env_file: str | None = ".env") -> Settings:
        raise SettingsError("invalid settings")

    monkeypatch.setattr(entrypoint.Settings, "from_env", classmethod(_raise_settings))

    assert entrypoint._run_service() == 1


def test_run_service_auto_cleanup_once_on_run_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)

    class FakeDateTime:
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> datetime:
            return datetime(2026, 2, 21, 10, 0, tzinfo=tz)

    class FakeStateRepo:
        last_instance: FakeStateRepo | None = None

        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            self.file_path = file_path
            self.logger = logger
            self.total_count = 7
            self.pending_count = 1
            self.cleanup_calls: list[tuple[int, bool, bool]] = []
            FakeStateRepo.last_instance = self

        def cleanup_stale(self, days: int, include_unsent: bool, dry_run: bool = False) -> int:
            self.cleanup_calls.append((days, include_unsent, dry_run))
            return 2

    class FakeWeatherClient:
        def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
            self.settings = settings
            self.logger = logger

    class FakeNotifier:
        last_instance: FakeNotifier | None = None

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.messages: list[str] = []
            FakeNotifier.last_instance = self

        def send(self, message: str, report_url: str | None = None) -> None:
            self.messages.append(message)

    class FakeProcessor:
        last_instance: FakeProcessor | None = None

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.calls = 0
            FakeProcessor.last_instance = self

        def run_once(self) -> CycleStats:
            self.calls += 1
            return CycleStats(
                start_date="20260221",
                end_date="20260222",
                area_count=1,
            )

    class FakeHealthStateRepo:
        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            self.file_path = file_path
            self.logger = logger

    class FakeHealthMonitor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def observe_cycle(self, **kwargs: object) -> ApiHealthDecision:
            return ApiHealthDecision(incident_open=False)

    logger = logging.getLogger("test.main.service")
    monkeypatch.setattr(entrypoint, "setup_logging", lambda *args, **kwargs: logger)
    monkeypatch.setattr(entrypoint, "datetime", FakeDateTime)
    monkeypatch.setattr(entrypoint, "JsonStateRepository", FakeStateRepo)
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

    result = entrypoint._run_service()
    repo = FakeStateRepo.last_instance
    processor = FakeProcessor.last_instance

    assert result == 0
    assert repo is not None
    assert processor is not None
    assert repo.cleanup_calls == [(30, True, False)]
    assert processor.calls == 1


def test_cleanup_state_command_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_cleanup_state(
        state_file: str,
        days: int,
        include_unsent: bool,
        dry_run: bool,
    ) -> int:
        captured.update(
            {
                "state_file": state_file,
                "days": days,
                "include_unsent": include_unsent,
                "dry_run": dry_run,
            }
        )
        return 0

    monkeypatch.setattr(entrypoint, "_cleanup_state", _fake_cleanup_state)

    result = entrypoint.main(
        [
            "cleanup-state",
            "--state-file",
            "tmp/state.json",
            "--days",
            "5",
            "--include-unsent",
            "--dry-run",
        ]
    )

    assert result == 0
    assert captured == {
        "state_file": "tmp/state.json",
        "days": 5,
        "include_unsent": True,
        "dry_run": True,
    }


def test_cleanup_state_rejects_negative_days() -> None:
    with pytest.raises(SystemExit) as exc:
        entrypoint.main(["cleanup-state", "--days", "-1"])
    assert exc.value.code == 2


def test_default_command_routes_to_run_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entrypoint, "_run_service", lambda: 7)
    assert entrypoint.main([]) == 7
    assert entrypoint.main(["run"]) == 7


def test_run_service_sends_health_alert_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        tmp_path,
        health_outage_min_failed_cycles=1,
        health_outage_consecutive_failures=1,
        run_once=True,
    )

    class FakeDateTime:
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> datetime:
            return datetime(2026, 2, 21, 10, 0, tzinfo=tz)

    class FakeStateRepo:
        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            self.file_path = file_path
            self.logger = logger
            self.total_count = 0
            self.pending_count = 0

        def cleanup_stale(self, days: int, include_unsent: bool, dry_run: bool = False) -> int:
            return 0

    class FakeHealthStateRepo:
        def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
            self.file_path = file_path
            self.logger = logger

    class FakeWeatherClient:
        def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
            self.settings = settings
            self.logger = logger

    class FakeNotifier:
        last_instance: FakeNotifier | None = None

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.messages: list[str] = []
            FakeNotifier.last_instance = self

        def send(self, message: str, report_url: str | None = None) -> None:
            self.messages.append(message)

    class FakeProcessor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run_once(self) -> CycleStats:
            return CycleStats(
                start_date="20260221",
                end_date="20260222",
                area_count=1,
                area_failures=1,
                api_error_counts={"timeout": 1},
                last_api_error="timeout",
            )

    class FakeHealthMonitor:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def observe_cycle(self, **kwargs: object) -> ApiHealthDecision:
            return ApiHealthDecision(
                incident_open=True,
                event="outage_detected",
                should_notify=True,
                outage_window_cycles=1,
                outage_window_failed_cycles=1,
                outage_window_fail_ratio=1.0,
                consecutive_severe_failures=1,
                representative_error="timeout",
            )

    logger = logging.getLogger("test.main.health")
    monkeypatch.setattr(entrypoint, "setup_logging", lambda *args, **kwargs: logger)
    monkeypatch.setattr(entrypoint, "datetime", FakeDateTime)
    monkeypatch.setattr(entrypoint, "JsonStateRepository", FakeStateRepo)
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

    result = entrypoint._run_service()
    notifier = FakeNotifier.last_instance

    assert result == 0
    assert notifier is not None
    assert len(notifier.messages) == 1
    assert notifier.messages[0].startswith("[API 장애 감지]")
