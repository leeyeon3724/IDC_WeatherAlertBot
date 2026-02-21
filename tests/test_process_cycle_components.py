from __future__ import annotations

import json
import logging
from datetime import datetime

import pytest

from app.domain.models import AlertEvent, AlertNotification
from app.observability import events
from app.repositories.state_models import StoredNotification
from app.services.weather_api import API_ERROR_TIMEOUT, WeatherApiError
from app.settings import Settings
from app.usecases.process_cycle_components import (
    AreaAlertFetcher,
    AreaFetchResult,
    CycleStats,
    CycleStatsRecorder,
    NotificationDispatcher,
    NotificationTracker,
)


class FakeWeatherClient:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, str, str, str]] = []
        self.closed = False

    def fetch_alerts(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]:
        self.calls.append((area_code, start_date, end_date, area_name))
        outcome = self.outcomes.get(area_code, [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def new_worker_client(self) -> FakeWeatherClient:
        return self

    def close(self) -> None:
        self.closed = True


class FakeStateRepository:
    def __init__(self) -> None:
        self.notifications: list[AlertNotification] = []
        self.unsent_rows: list[StoredNotification] = []
        self.marked_ids: list[str] = []

    def upsert_notifications(self, notifications) -> int:
        saved = list(notifications)
        self.notifications.extend(saved)
        return len(saved)

    def get_unsent(self, area_code: str | None = None) -> list[StoredNotification]:
        if area_code is None:
            return list(self.unsent_rows)
        return [row for row in self.unsent_rows if row.area_code == area_code]

    def mark_sent(self, event_id: str) -> bool:
        self.marked_ids.append(event_id)
        return True

    def mark_many_sent(self, event_ids) -> int:
        marked = list(event_ids)
        self.marked_ids.extend(marked)
        return len(marked)

    def cleanup_stale(
        self,
        *,
        days: int = 30,
        include_unsent: bool = False,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> int:
        return 0

    @property
    def total_count(self) -> int:
        return len(self.notifications)

    @property
    def pending_count(self) -> int:
        return len([row for row in self.unsent_rows if not row.sent])


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None]] = []

    def send(self, message: str, report_url: str | None = None) -> None:
        self.sent.append((message, report_url))


def _settings(tmp_path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "service_api_key": "test-key",
        "service_hook_url": "https://hook.example",
        "weather_alert_data_api_url": "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd",
        "sent_messages_file": tmp_path / "state.json",
        "area_codes": ["11B00000", "11C00000"],
        "area_code_mapping": {"11B00000": "서울", "11C00000": "경기"},
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
        "notifier_max_attempts_per_cycle": 100,
        "area_max_workers": 1,
        "lookback_days": 0,
        "cycle_interval_sec": 0,
        "area_interval_sec": 0,
        "cleanup_enabled": False,
        "cleanup_retention_days": 30,
        "cleanup_include_unsent": False,
        "bot_name": "테스트봇",
        "timezone": "Asia/Seoul",
        "log_level": "INFO",
        "dry_run": False,
        "run_once": True,
    }
    base.update(overrides)
    return Settings(**base)


def _sample_alert(**overrides: object) -> AlertEvent:
    base: dict[str, object] = {
        "area_code": "11B00000",
        "area_name": "서울",
        "warn_var": "호우",
        "warn_stress": "주의보",
        "command": "발표",
        "cancel": "정상",
        "start_time": "2026년 2월 20일 오전 9시",
        "end_time": "2026년 2월 20일 오후 6시",
        "stn_id": "109",
        "tm_fc": "202602200900",
        "tm_seq": "1",
    }
    base.update(overrides)
    return AlertEvent(**base)


def test_area_alert_fetcher_handles_serial_results_and_interval_sleep(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path, area_max_workers=1, area_interval_sec=2)
    weather_client = FakeWeatherClient(
        {
            "11B00000": [_sample_alert(area_code="11B00000", area_name="서울")],
            "11C00000": WeatherApiError("timeout", code=API_ERROR_TIMEOUT),
        }
    )
    fetcher = AreaAlertFetcher(
        settings=settings,
        weather_client=weather_client,
        logger=logging.getLogger("test.fetcher.serial"),
    )

    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "app.usecases.process_cycle_components.time.sleep",
        lambda value: sleep_calls.append(value),
    )

    results = fetcher.fetch_alerts_for_areas(start_date="20260220", end_date="20260221")

    assert set(results) == {"11B00000", "11C00000"}
    assert results["11B00000"].error is None
    assert results["11C00000"].error is not None
    assert sleep_calls == [2]


def test_area_alert_fetcher_resolve_result_returns_missing_error_when_absent(tmp_path) -> None:
    settings = _settings(tmp_path)
    fetcher = AreaAlertFetcher(
        settings=settings,
        weather_client=FakeWeatherClient({}),
        logger=logging.getLogger("test.fetcher.resolve"),
    )

    resolved = fetcher.resolve_area_result("11B00000", {})

    assert resolved.error is not None
    assert isinstance(resolved.error, WeatherApiError)
    assert resolved.error.code == "missing_area_fetch_result"


def test_notification_tracker_tracks_notifications_and_url_validation_warnings(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path)
    state_repo = FakeStateRepository()
    logger = logging.getLogger("test.tracker")
    tracker = NotificationTracker(settings=settings, state_repo=state_repo, logger=logger)
    stats = CycleStats(start_date="20260220", end_date="20260221")

    invalid_alert = _sample_alert(stn_id="109", tm_fc="", tm_seq="1")
    area_result = AreaFetchResult(
        area_code="11B00000",
        area_name="서울",
        alerts=[invalid_alert],
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        tracker.track_area_notifications(area_code="11B00000", result=area_result, stats=stats)

    assert stats.alerts_fetched == 1
    assert stats.newly_tracked == 1
    assert len(state_repo.notifications) == 1

    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(
        payload.get("event") == events.NOTIFICATION_URL_ATTACHMENT_BLOCKED
        and payload.get("reason") == "incomplete_report_params"
        for payload in payloads
    )


def test_notification_dispatcher_applies_backpressure_and_marks_sent(tmp_path) -> None:
    settings = _settings(tmp_path, notifier_max_attempts_per_cycle=1)
    state_repo = FakeStateRepository()
    state_repo.unsent_rows = [
        StoredNotification(
            event_id="event:1",
            area_code="11B00000",
            message="m1",
            report_url=None,
            sent=False,
            first_seen_at="2026-02-20T00:00:00Z",
            updated_at="2026-02-20T00:00:00Z",
            last_sent_at=None,
        ),
        StoredNotification(
            event_id="event:2",
            area_code="11B00000",
            message="m2",
            report_url=None,
            sent=False,
            first_seen_at="2026-02-20T00:00:00Z",
            updated_at="2026-02-20T00:00:00Z",
            last_sent_at=None,
        ),
    ]
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(
        settings=settings,
        notifier=notifier,
        state_repo=state_repo,
        logger=logging.getLogger("test.dispatcher"),
    )
    stats = CycleStats(start_date="20260220", end_date="20260221")

    dispatcher.dispatch_unsent_for_area(area_code="11B00000", stats=stats)

    assert stats.notification_attempts == 1
    assert stats.notification_backpressure_skips == 1
    assert stats.sent_count == 1
    assert notifier.sent == [("m1", None)]
    assert state_repo.marked_ids == ["event:1"]


def test_cycle_stats_recorder_tracks_failure_counts_and_last_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("test.stats")
    recorder = CycleStatsRecorder(logger=logger)
    stats = CycleStats(start_date="20260220", end_date="20260221")
    result = AreaFetchResult(
        area_code="11B00000",
        area_name="서울",
        alerts=None,
        error=WeatherApiError("timeout", code=API_ERROR_TIMEOUT),
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        recorder.record_area_failure(area_code="11B00000", result=result, stats=stats)

    assert stats.area_failures == 1
    assert stats.api_error_counts[API_ERROR_TIMEOUT] == 1
    assert stats.last_api_error is not None
