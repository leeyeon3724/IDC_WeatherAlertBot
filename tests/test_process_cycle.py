from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.models import AlertEvent
from app.repositories.state_repo import JsonStateRepository
from app.services.notifier import NotificationError
from app.services.weather_api import API_ERROR_TIMEOUT, WeatherApiError
from app.settings import Settings
from app.usecases.process_cycle import ProcessCycleUseCase


class FakeWeatherClient:
    def __init__(self, alerts_by_area):
        self.alerts_by_area = alerts_by_area
        self.calls: list[tuple[str, str, str, str]] = []

    def fetch_alerts(self, area_code: str, start_date: str, end_date: str, area_name: str):
        self.calls.append((area_code, start_date, end_date, area_name))
        outcome = self.alerts_by_area.get(area_code, [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeNotifier:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.sent_messages: list[tuple[str, str | None]] = []

    def send(self, message: str, report_url: str | None = None) -> None:
        if self.should_fail:
            raise NotificationError("forced notifier failure")
        self.sent_messages.append((message, report_url))


def _settings(tmp_path) -> Settings:
    return Settings(
        service_api_key="test-key",
        service_hook_url="https://hook.example",
        weather_alert_data_api_url="https://api.example",
        sent_messages_file=tmp_path / "state.json",
        area_codes=["11B00000"],
        area_code_mapping={"11B00000": "서울"},
        request_timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        cycle_interval_sec=0,
        area_interval_sec=0,
        bot_name="테스트봇",
        timezone="Asia/Seoul",
        log_level="INFO",
    )


def _sample_alert() -> AlertEvent:
    return AlertEvent(
        area_code="11B00000",
        area_name="서울",
        warn_var="호우",
        warn_stress="주의보",
        command="발표",
        cancel="정상",
        start_time="2026년 2월 20일 오전 9시",
        end_time="2026년 2월 20일 오후 6시",
        stn_id="109",
        tm_fc="202602200900",
        tm_seq="1",
    )


def test_process_cycle_tracks_and_sends_once(tmp_path) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": [_sample_alert()]})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor"),
    )

    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    first = usecase.run_once(now=now)
    second = usecase.run_once(now=now)

    assert first.newly_tracked == 1
    assert first.sent_count == 1
    assert first.pending_total == 0
    assert second.newly_tracked == 0
    assert second.sent_count == 0
    assert len(notifier.sent_messages) == 1


def test_process_cycle_retries_unsent_on_next_cycle(tmp_path) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": [_sample_alert()]})
    fail_notifier = FakeNotifier(should_fail=True)

    failing_usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=fail_notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.fail"),
    )

    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    fail_stats = failing_usecase.run_once(now=now)
    assert fail_stats.send_failures == 1
    assert fail_stats.pending_total == 1

    success_notifier = FakeNotifier(should_fail=False)
    retry_usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=success_notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.retry"),
    )
    success_stats = retry_usecase.run_once(now=now)
    assert success_stats.sent_count == 1
    assert success_stats.pending_total == 0


def test_process_cycle_dry_run_does_not_send_or_mark(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings = Settings(
        **{**settings.__dict__, "dry_run": True, "run_once": True},
    )
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": [_sample_alert()]})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.dryrun"),
    )

    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    stats = usecase.run_once(now=now)
    assert stats.newly_tracked == 1
    assert stats.sent_count == 0
    assert stats.pending_total == 1
    assert notifier.sent_messages == []


def test_process_cycle_applies_lookback_days(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings = Settings(**{**settings.__dict__, "lookback_days": 2})
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": []})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.lookback"),
    )

    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    stats = usecase.run_once(now=now)
    assert stats.start_date == "20260218"
    assert stats.end_date == "20260221"
    assert weather_client.calls[0][1] == "20260218"


def test_process_cycle_parallel_fetch_ignores_area_interval(tmp_path) -> None:
    settings = Settings(
        service_api_key="test-key",
        service_hook_url="https://hook.example",
        weather_alert_data_api_url="https://api.example",
        sent_messages_file=tmp_path / "state.json",
        area_codes=["11B00000", "11C00000"],
        area_code_mapping={"11B00000": "서울", "11C00000": "경기"},
        request_timeout_sec=1,
        request_connect_timeout_sec=1,
        request_read_timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        notifier_timeout_sec=1,
        notifier_connect_timeout_sec=1,
        notifier_read_timeout_sec=1,
        notifier_max_retries=1,
        notifier_retry_delay_sec=0,
        area_max_workers=2,
        lookback_days=0,
        cycle_interval_sec=0,
        area_interval_sec=2,
        cleanup_enabled=False,
        cleanup_retention_days=30,
        cleanup_include_unsent=True,
        bot_name="테스트봇",
        timezone="Asia/Seoul",
        log_level="INFO",
        dry_run=True,
        run_once=True,
    )
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": [], "11C00000": []})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.parallel"),
    )

    start = time.perf_counter()
    usecase.run_once(now=datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")))
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0


def test_process_cycle_records_api_error_codes(tmp_path) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient(
        {
            "11B00000": WeatherApiError(
                "temporary timeout",
                code=API_ERROR_TIMEOUT,
            )
        }
    )
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.error_code"),
    )

    stats = usecase.run_once(now=datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")))
    assert stats.area_count == 1
    assert stats.areas_processed == 1
    assert stats.area_failures == 1
    assert stats.api_error_counts[API_ERROR_TIMEOUT] == 1
    assert stats.last_api_error is not None


def test_process_cycle_lookback_override(tmp_path) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": []})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.lookback.override"),
    )

    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    stats = usecase.run_once(now=now, lookback_days_override=3)
    assert stats.start_date == "20260217"
    assert stats.end_date == "20260221"
    assert weather_client.calls[0][1] == "20260217"
