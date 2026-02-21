from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Protocol

from app.domain.message_builder import build_notification
from app.domain.models import AlertEvent
from app.logging_utils import log_event, redact_sensitive_text
from app.observability import events
from app.repositories.state_repository import StateRepository
from app.services.notifier import DoorayNotifier, NotificationError
from app.services.weather_api import WeatherApiError, WeatherClient
from app.settings import Settings


@dataclass
class CycleStats:
    start_date: str
    end_date: str
    area_count: int = 0
    areas_processed: int = 0
    area_failures: int = 0
    alerts_fetched: int = 0
    api_fetch_calls: int = 0
    newly_tracked: int = 0
    notification_attempts: int = 0
    sent_count: int = 0
    send_failures: int = 0
    notification_dry_run_skips: int = 0
    notification_backpressure_skips: int = 0
    pending_total: int = 0
    api_error_counts: dict[str, int] = field(default_factory=dict)
    last_api_error: str | None = None


@dataclass
class AreaFetchResult:
    area_code: str
    area_name: str
    alerts: list[AlertEvent] | None
    error: Exception | None = None


class AreaAlertFetcherProtocol(Protocol):
    def fetch_alerts_for_areas(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, AreaFetchResult]: ...

    def resolve_area_result(
        self,
        area_code: str,
        area_results: dict[str, AreaFetchResult],
    ) -> AreaFetchResult: ...


class CycleStatsRecorderProtocol(Protocol):
    def record_area_failure(
        self,
        *,
        area_code: str,
        result: AreaFetchResult,
        stats: CycleStats,
    ) -> None: ...


class NotificationTrackerProtocol(Protocol):
    def track_area_notifications(
        self,
        *,
        area_code: str,
        result: AreaFetchResult,
        stats: CycleStats,
    ) -> None: ...


class NotificationDispatcherProtocol(Protocol):
    def dispatch_unsent_for_area(self, *, area_code: str, stats: CycleStats) -> None: ...


class AreaAlertFetcher:
    def __init__(
        self,
        *,
        settings: Settings,
        weather_client: WeatherClient,
        logger: logging.Logger,
    ) -> None:
        self.settings = settings
        self.weather_client = weather_client
        self.logger = logger

    def fetch_alerts_for_areas(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, AreaFetchResult]:
        results: dict[str, AreaFetchResult] = {}
        area_count = len(self.settings.area_codes)

        if area_count == 0:
            return results

        if self.settings.area_max_workers <= 1 or area_count == 1:
            last_index = area_count - 1
            for idx, area_code in enumerate(self.settings.area_codes):
                area_name = self.settings.area_code_mapping.get(area_code, "알 수 없는 지역")
                try:
                    alerts = self.weather_client.fetch_alerts(
                        area_code=area_code,
                        start_date=start_date,
                        end_date=end_date,
                        area_name=area_name,
                    )
                    results[area_code] = AreaFetchResult(
                        area_code=area_code,
                        area_name=area_name,
                        alerts=alerts,
                    )
                except Exception as exc:
                    results[area_code] = AreaFetchResult(
                        area_code=area_code,
                        area_name=area_name,
                        alerts=None,
                        error=exc,
                    )
                finally:
                    if idx < last_index and self.settings.area_interval_sec > 0:
                        time.sleep(self.settings.area_interval_sec)
            return results

        max_workers = min(self.settings.area_max_workers, area_count)
        self.logger.info(
            log_event(events.CYCLE_PARALLEL_FETCH, workers=max_workers, area_count=area_count)
        )
        if self.settings.area_interval_sec > 0:
            self.logger.info(
                log_event(
                    events.CYCLE_AREA_INTERVAL_IGNORED,
                    reason="parallel_fetch_enabled",
                    area_interval_sec=self.settings.area_interval_sec,
                )
            )

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="area-fetch",
        ) as executor:
            future_to_area = {}
            for area_code in self.settings.area_codes:
                area_name = self.settings.area_code_mapping.get(area_code, "알 수 없는 지역")
                future = executor.submit(
                    self._fetch_alerts_with_worker_client,
                    area_code,
                    start_date,
                    end_date,
                    area_name,
                )
                future_to_area[future] = (area_code, area_name)

            for future in as_completed(future_to_area):
                area_code, area_name = future_to_area[future]
                try:
                    alerts = future.result()
                    results[area_code] = AreaFetchResult(
                        area_code=area_code,
                        area_name=area_name,
                        alerts=alerts,
                    )
                except Exception as exc:
                    results[area_code] = AreaFetchResult(
                        area_code=area_code,
                        area_name=area_name,
                        alerts=None,
                        error=exc,
                    )
        return results

    def _fetch_alerts_with_worker_client(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]:
        worker_client = self.weather_client.new_worker_client()
        try:
            return worker_client.fetch_alerts(
                area_code=area_code,
                start_date=start_date,
                end_date=end_date,
                area_name=area_name,
            )
        finally:
            worker_client.close()

    def resolve_area_result(
        self,
        area_code: str,
        area_results: dict[str, AreaFetchResult],
    ) -> AreaFetchResult:
        return area_results.get(
            area_code,
            AreaFetchResult(
                area_code=area_code,
                area_name=self.settings.area_code_mapping.get(area_code, "알 수 없는 지역"),
                alerts=None,
                error=WeatherApiError("missing_area_result", code="missing_area_fetch_result"),
            ),
        )


class CycleStatsRecorder:
    def __init__(self, *, logger: logging.Logger) -> None:
        self.logger = logger

    @staticmethod
    def api_error_code(error: Exception) -> str:
        if isinstance(error, WeatherApiError):
            return error.code
        return "unknown_error"

    def record_area_failure(
        self,
        *,
        area_code: str,
        result: AreaFetchResult,
        stats: CycleStats,
    ) -> None:
        stats.area_failures += 1
        error_code = self.api_error_code(result.error or WeatherApiError("unknown"))
        stats.api_error_counts[error_code] = stats.api_error_counts.get(error_code, 0) + 1
        stats.last_api_error = str(result.error or "unknown")
        self.logger.error(
            log_event(
                events.AREA_FAILED,
                area_code=area_code,
                error_code=error_code,
                error=redact_sensitive_text(result.error),
            )
        )


class NotificationTracker:
    def __init__(
        self,
        *,
        settings: Settings,
        state_repo: StateRepository,
        logger: logging.Logger,
    ) -> None:
        self.settings = settings
        self.state_repo = state_repo
        self.logger = logger

    def track_area_notifications(
        self,
        *,
        area_code: str,
        result: AreaFetchResult,
        stats: CycleStats,
    ) -> None:
        alerts = result.alerts or []
        stats.alerts_fetched += len(alerts)

        notifications = [
            build_notification(alert, rules=self.settings.alert_rules.message_rules)
            for alert in alerts
        ]
        for notification in notifications:
            if notification.url_validation_error:
                self.logger.warning(
                    log_event(
                        events.NOTIFICATION_URL_ATTACHMENT_BLOCKED,
                        event_id=notification.event_id,
                        area_code=notification.area_code,
                        reason=notification.url_validation_error,
                    )
                )
        stats.newly_tracked += self.state_repo.upsert_notifications(notifications)


class NotificationDispatcher:
    def __init__(
        self,
        *,
        settings: Settings,
        notifier: DoorayNotifier,
        state_repo: StateRepository,
        logger: logging.Logger,
    ) -> None:
        self.settings = settings
        self.notifier = notifier
        self.state_repo = state_repo
        self.logger = logger

    def dispatch_unsent_for_area(self, *, area_code: str, stats: CycleStats) -> None:
        successful_event_ids: list[str] = []
        unsent_rows = self.state_repo.get_unsent(area_code=area_code)
        max_attempts_per_cycle = self.settings.notifier_max_attempts_per_cycle
        for index, row in enumerate(unsent_rows):
            if (
                max_attempts_per_cycle > 0
                and stats.notification_attempts >= max_attempts_per_cycle
            ):
                skipped = len(unsent_rows) - index
                stats.notification_backpressure_skips += skipped
                self.logger.warning(
                    log_event(
                        events.NOTIFICATION_BACKPRESSURE_APPLIED,
                        area_code=area_code,
                        max_attempts_per_cycle=max_attempts_per_cycle,
                        skipped=skipped,
                    )
                )
                break
            if self.settings.dry_run:
                stats.notification_dry_run_skips += 1
                self.logger.info(
                    log_event(
                        events.NOTIFICATION_DRY_RUN,
                        event_id=row.event_id,
                        area_code=row.area_code,
                    )
                )
                continue
            try:
                stats.notification_attempts += 1
                self.notifier.send(row.message, report_url=row.report_url)
                successful_event_ids.append(row.event_id)
            except NotificationError as exc:
                stats.send_failures += 1
                self.logger.error(
                    log_event(
                        events.NOTIFICATION_FINAL_FAILURE,
                        event_id=row.event_id,
                        area_code=row.area_code,
                        attempts=exc.attempts,
                        error=redact_sensitive_text(exc.last_error or exc),
                    )
                )

        if successful_event_ids:
            marked_count = self.state_repo.mark_many_sent(successful_event_ids)
            stats.sent_count += marked_count
            for event_id in successful_event_ids:
                self.logger.info(
                    log_event(
                        events.NOTIFICATION_SENT,
                        event_id=event_id,
                        area_code=area_code,
                    )
                )
