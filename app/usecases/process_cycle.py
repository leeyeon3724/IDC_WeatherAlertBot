from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.logging_utils import log_event
from app.observability import events
from app.repositories.state_repository import StateRepository
from app.services.notifier import DoorayNotifier
from app.services.weather_api import WeatherClient
from app.settings import Settings
from app.usecases.process_cycle_components import (
    AreaAlertFetcher,
    AreaAlertFetcherProtocol,
    AreaFetchResult,
    CycleStats,
    CycleStatsRecorder,
    CycleStatsRecorderProtocol,
    NotificationDispatcher,
    NotificationDispatcherProtocol,
    NotificationTracker,
    NotificationTrackerProtocol,
)


class ProcessCycleUseCase:
    def __init__(
        self,
        settings: Settings,
        weather_client: WeatherClient,
        notifier: DoorayNotifier,
        state_repo: StateRepository,
        logger: logging.Logger | None = None,
        *,
        alert_fetcher: AreaAlertFetcherProtocol | None = None,
        notification_tracker: NotificationTrackerProtocol | None = None,
        notification_dispatcher: NotificationDispatcherProtocol | None = None,
        stats_recorder: CycleStatsRecorderProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.weather_client = weather_client
        self.notifier = notifier
        self.state_repo = state_repo
        self.logger = logger or logging.getLogger("weather_alert_bot.processor")
        self._dispatch_start_index = 0

        self.alert_fetcher: AreaAlertFetcherProtocol = alert_fetcher or AreaAlertFetcher(
            settings=settings,
            weather_client=weather_client,
            logger=self.logger,
        )
        self.notification_tracker: NotificationTrackerProtocol = (
            notification_tracker
            or NotificationTracker(
                settings=settings,
                state_repo=state_repo,
                logger=self.logger,
            )
        )
        self.notification_dispatcher: NotificationDispatcherProtocol = (
            notification_dispatcher
            or NotificationDispatcher(
                settings=settings,
                notifier=notifier,
                state_repo=state_repo,
                logger=self.logger,
            )
        )
        self.stats_recorder: CycleStatsRecorderProtocol = stats_recorder or CycleStatsRecorder(
            logger=self.logger
        )

    def close(self) -> None:
        self.weather_client.close()

    def _resolve_area_result(
        self,
        area_code: str,
        area_results: dict[str, AreaFetchResult],
    ) -> AreaFetchResult:
        return self.alert_fetcher.resolve_area_result(area_code, area_results)

    def _area_codes_for_cycle(self) -> list[str]:
        area_codes = list(self.settings.area_codes)
        area_count = len(area_codes)
        if area_count <= 1:
            return area_codes

        start = self._dispatch_start_index % area_count
        ordered_codes = area_codes[start:] + area_codes[:start]
        self._dispatch_start_index = (start + 1) % area_count
        return ordered_codes

    def run_once(
        self,
        now: datetime | None = None,
        lookback_days_override: int | None = None,
    ) -> CycleStats:
        tz = ZoneInfo(self.settings.timezone)
        current = now or datetime.now(tz)
        lookback_days = (
            lookback_days_override
            if lookback_days_override is not None
            else self.settings.lookback_days
        )
        lookback_days = max(lookback_days, 0)
        start_base = current - timedelta(days=lookback_days)
        start_date = start_base.strftime("%Y%m%d")
        end_date = (current + timedelta(days=1)).strftime("%Y%m%d")
        return self.run_date_range(start_date=start_date, end_date=end_date)

    def run_date_range(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> CycleStats:
        if start_date >= end_date:
            raise ValueError(
                "start_date must be earlier than end_date "
                f"(received start_date={start_date}, end_date={end_date})."
            )

        stats = CycleStats(
            start_date=start_date,
            end_date=end_date,
            area_count=len(self.settings.area_codes),
        )

        self.logger.info(
            log_event(
                events.CYCLE_START,
                start_date=start_date,
                end_date=end_date,
                area_count=len(self.settings.area_codes),
            )
        )

        area_results = self.alert_fetcher.fetch_alerts_for_areas(
            start_date=start_date,
            end_date=end_date,
        )
        stats.api_fetch_calls = len(area_results)

        for area_code in self._area_codes_for_cycle():
            stats.areas_processed += 1
            result = self._resolve_area_result(area_code=area_code, area_results=area_results)
            self.logger.info(
                log_event(events.AREA_START, area_code=area_code, area_name=result.area_name)
            )
            if result.error is not None:
                self.stats_recorder.record_area_failure(
                    area_code=area_code,
                    result=result,
                    stats=stats,
                )
                continue

            self.notification_tracker.track_area_notifications(
                area_code=area_code,
                result=result,
                stats=stats,
            )
            self.notification_dispatcher.dispatch_unsent_for_area(
                area_code=area_code,
                stats=stats,
            )

        stats.pending_total = self.state_repo.pending_count
        return stats
