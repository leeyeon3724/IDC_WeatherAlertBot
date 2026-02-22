from __future__ import annotations

import logging
from pathlib import Path

from app.repositories.json_state_repo import JsonStateRepository
from app.settings import Settings
from app.usecases.process_cycle import ProcessCycleUseCase
from app.usecases.process_cycle_components import (
    AreaAlertFetcherProtocol,
    AreaFetchResult,
    CycleStats,
    CycleStatsRecorderProtocol,
    NotificationDispatcherProtocol,
    NotificationTrackerProtocol,
)
from tests.main_test_harness import make_settings


class _FakeWeatherClient:
    def __init__(self) -> None:
        self.closed = False

    def fetch_alerts(self, area_code: str, start_date: str, end_date: str, area_name: str):
        return []

    def new_worker_client(self) -> _FakeWeatherClient:
        return self

    def close(self) -> None:
        self.closed = True


class _FakeNotifier:
    def send(self, message: str, report_url: str | None = None) -> None:
        return None


class _StubFetcher:
    def __init__(self, area_code: str, area_name: str) -> None:
        self.area_code = area_code
        self.area_name = area_name
        self.fetch_calls = 0

    def fetch_alerts_for_areas(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, AreaFetchResult]:
        self.fetch_calls += 1
        return {
            self.area_code: AreaFetchResult(
                area_code=self.area_code,
                area_name=self.area_name,
                alerts=[],
            )
        }

    def resolve_area_result(
        self,
        area_code: str,
        area_results: dict[str, AreaFetchResult],
    ) -> AreaFetchResult:
        return area_results[area_code]


class _StubTracker:
    def __init__(self) -> None:
        self.calls = 0

    def track_area_notifications(
        self,
        *,
        area_code: str,
        result: AreaFetchResult,
        stats: CycleStats,
    ) -> None:
        self.calls += 1


class _StubDispatcher:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch_unsent_for_area(self, *, area_code: str, stats: CycleStats) -> None:
        self.calls += 1


class _StubStatsRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def record_area_failure(
        self,
        *,
        area_code: str,
        result: AreaFetchResult,
        stats: CycleStats,
    ) -> None:
        self.calls += 1


def test_process_cycle_accepts_protocol_based_components(tmp_path: Path) -> None:
    settings: Settings = make_settings(tmp_path)
    state_repo = JsonStateRepository(settings.sent_messages_file)
    weather_client = _FakeWeatherClient()
    notifier = _FakeNotifier()

    fetcher: AreaAlertFetcherProtocol = _StubFetcher("L1070100", "대구")
    tracker: NotificationTrackerProtocol = _StubTracker()
    dispatcher: NotificationDispatcherProtocol = _StubDispatcher()
    stats_recorder: CycleStatsRecorderProtocol = _StubStatsRecorder()

    usecase = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=state_repo,
        logger=logging.getLogger("test.process_cycle.protocols"),
        alert_fetcher=fetcher,
        notification_tracker=tracker,
        notification_dispatcher=dispatcher,
        stats_recorder=stats_recorder,
    )

    stats = usecase.run_date_range(start_date="20260220", end_date="20260221")

    assert stats.api_fetch_calls == 1
    assert stats.areas_processed == 1
    assert isinstance(fetcher, _StubFetcher) and fetcher.fetch_calls == 1
    assert isinstance(tracker, _StubTracker) and tracker.calls == 1
    assert isinstance(dispatcher, _StubDispatcher) and dispatcher.calls == 1
    assert isinstance(stats_recorder, _StubStatsRecorder) and stats_recorder.calls == 0

    usecase.close()
    assert weather_client.closed is True
