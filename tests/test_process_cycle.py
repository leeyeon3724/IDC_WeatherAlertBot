from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.models import AlertEvent, AlertNotification
from app.observability import events
from app.repositories.json_state_repo import JsonStateRepository
from app.services.notifier import NotificationError
from app.services.weather_api import API_ERROR_TIMEOUT, WeatherAlertClient, WeatherApiError
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

    def new_worker_client(self) -> FakeWeatherClient:
        return self

    def close(self) -> None:
        pass


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
    assert first.api_fetch_calls == 1
    assert first.notification_attempts == 1
    assert first.notification_dry_run_skips == 0
    assert first.sent_count == 1
    assert first.pending_total == 0
    assert second.newly_tracked == 0
    assert second.notification_attempts == 0
    assert second.notification_dry_run_skips == 0
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
    assert fail_stats.api_fetch_calls == 1
    assert fail_stats.notification_attempts == 1
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
    assert success_stats.notification_attempts == 1
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
    assert stats.api_fetch_calls == 1
    assert stats.notification_attempts == 0
    assert stats.notification_dry_run_skips == 1
    assert stats.sent_count == 0
    assert stats.pending_total == 1
    assert notifier.sent_messages == []


def test_process_cycle_applies_notification_backpressure_budget(tmp_path) -> None:
    settings = Settings(
        **{
            **_settings(tmp_path).__dict__,
            "notifier_max_attempts_per_cycle": 1,
        }
    )
    repo = JsonStateRepository(settings.sent_messages_file)
    second_alert = AlertEvent(
        area_code="11B00000",
        area_name="서울",
        warn_var="강풍",
        warn_stress="주의보",
        command="발표",
        cancel="정상",
        start_time="2026년 2월 20일 오전 10시",
        end_time="2026년 2월 20일 오후 7시",
        stn_id="109",
        tm_fc="202602201000",
        tm_seq="2",
    )
    weather_client = FakeWeatherClient({"11B00000": [_sample_alert(), second_alert]})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.backpressure"),
    )

    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    stats = usecase.run_once(now=now)

    assert stats.newly_tracked == 2
    assert stats.notification_attempts == 1
    assert stats.notification_backpressure_skips == 1
    assert stats.sent_count == 1
    assert stats.pending_total == 1
    assert len(notifier.sent_messages) == 1


def test_process_cycle_rotates_dispatch_order_under_backpressure(tmp_path) -> None:
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
        notifier_max_attempts_per_cycle=1,
        area_max_workers=1,
        lookback_days=0,
        cycle_interval_sec=0,
        area_interval_sec=0,
        cleanup_enabled=False,
        cleanup_retention_days=30,
        cleanup_include_unsent=False,
        bot_name="테스트봇",
        timezone="Asia/Seoul",
        log_level="INFO",
        dry_run=False,
        run_once=True,
    )
    repo = JsonStateRepository(settings.sent_messages_file)
    repo.upsert_notifications(
        [
            AlertNotification(
                event_id="event:seoul",
                area_code="11B00000",
                message="서울 대기 알림",
                report_url=None,
            ),
            AlertNotification(
                event_id="event:gyeonggi",
                area_code="11C00000",
                message="경기 대기 알림",
                report_url=None,
            ),
        ]
    )
    weather_client = FakeWeatherClient({"11B00000": [], "11C00000": []})
    notifier = FakeNotifier(should_fail=False)
    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.fairness"),
    )
    now = datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    first = usecase.run_once(now=now)
    second = usecase.run_once(now=now)

    assert first.notification_attempts == 1
    assert first.notification_backpressure_skips == 1
    assert first.pending_total == 1
    assert second.notification_attempts == 1
    assert second.notification_backpressure_skips == 0
    assert second.pending_total == 0
    assert [message for message, _ in notifier.sent_messages] == [
        "서울 대기 알림",
        "경기 대기 알림",
    ]


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


def test_process_cycle_supports_explicit_date_range(tmp_path) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": []})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.range"),
    )

    stats = usecase.run_date_range(start_date="20260210", end_date="20260212")
    assert stats.start_date == "20260210"
    assert stats.end_date == "20260212"
    assert weather_client.calls[0][1] == "20260210"
    assert weather_client.calls[0][2] == "20260212"


def test_process_cycle_rejects_invalid_date_range(tmp_path) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": []})
    notifier = FakeNotifier(should_fail=False)

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.invalid_range"),
    )

    with pytest.raises(ValueError):
        usecase.run_date_range(start_date="20260212", end_date="20260212")


def test_process_cycle_parallel_fetch_ignores_area_interval(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "app.usecases.process_cycle.time.sleep",
        lambda value: sleep_calls.append(value),
    )
    usecase.run_once(now=datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")))

    assert sleep_calls == []
    assert len(weather_client.calls) == 2


def test_process_cycle_parallel_fetch_uses_isolated_weather_clients(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        area_interval_sec=0,
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
    weather_client = WeatherAlertClient(
        settings=settings,
        logger=logging.getLogger("test.processor.parallel.worker_client"),
    )
    notifier = FakeNotifier(should_fail=False)

    fetched_client_ids: list[int] = []

    def _fake_fetch_alerts(
        self: WeatherAlertClient,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]:
        fetched_client_ids.append(id(self))
        return []

    monkeypatch.setattr(WeatherAlertClient, "fetch_alerts", _fake_fetch_alerts)
    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logging.getLogger("test.processor.parallel.worker_client"),
    )
    usecase.run_once(now=datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")))

    assert len(fetched_client_ids) == 2
    assert len(set(fetched_client_ids)) == 2
    assert id(weather_client) not in set(fetched_client_ids)


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
    assert stats.api_fetch_calls == 1
    assert stats.notification_attempts == 0
    assert stats.area_failures == 1
    assert stats.api_error_counts[API_ERROR_TIMEOUT] == 1
    assert stats.last_api_error is not None


def test_process_cycle_missing_area_result_uses_specific_error_code(tmp_path) -> None:
    """_resolve_area_result에서 결과가 없을 때 오류 코드가 missing_area_fetch_result여야 한다."""
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=FakeWeatherClient({}),
        notifier=FakeNotifier(should_fail=False),
        state_repo=repo,
        logger=logging.getLogger("test.missing_area"),
    )

    result = usecase._resolve_area_result("11B00000", {})
    assert result.error is not None
    assert result.error.code == "missing_area_fetch_result"


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


def test_process_cycle_redacts_sensitive_values_in_area_failure_log(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient(
        {
            "11B00000": WeatherApiError(
                "fetch failed serviceKey=RAW-KEY&apiKey=RAW-API&SERVICE_API_KEY=RAW-ENV",
                code=API_ERROR_TIMEOUT,
            )
        }
    )
    notifier = FakeNotifier(should_fail=False)
    logger = logging.getLogger("test.processor.redaction.area")

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=repo,
        logger=logger,
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        usecase.run_once(now=datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")))

    payloads = [json.loads(record.message) for record in caplog.records]
    area_failed = [payload for payload in payloads if payload.get("event") == events.AREA_FAILED]
    assert len(area_failed) == 1
    error_text = str(area_failed[0].get("error"))
    assert "RAW-KEY" not in error_text
    assert "RAW-API" not in error_text
    assert "RAW-ENV" not in error_text
    assert "serviceKey=***" in error_text
    assert "apiKey=***" in error_text
    assert "SERVICE_API_KEY=***" in error_text


def test_process_cycle_redacts_sensitive_values_in_notification_failure_log(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path)
    repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = FakeWeatherClient({"11B00000": [_sample_alert()]})
    logger = logging.getLogger("test.processor.redaction.notification")

    class _SecretFailingNotifier:
        def send(self, message: str, report_url: str | None = None) -> None:
            raise NotificationError(
                "forced failure",
                attempts=2,
                last_error=RuntimeError("apiKey=RAW-API service_api_key=RAW-ENV"),
            )

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=_SecretFailingNotifier(),
        state_repo=repo,
        logger=logger,
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        stats = usecase.run_once(now=datetime(2026, 2, 20, 10, 0, tzinfo=ZoneInfo("Asia/Seoul")))

    assert stats.send_failures == 1
    payloads = [json.loads(record.message) for record in caplog.records]
    failures = [
        payload for payload in payloads if payload.get("event") == events.NOTIFICATION_FINAL_FAILURE
    ]
    assert len(failures) == 1
    error_text = str(failures[0].get("error"))
    assert "RAW-API" not in error_text
    assert "RAW-ENV" not in error_text
    assert "apiKey=***" in error_text
    assert "service_api_key=***" in error_text
