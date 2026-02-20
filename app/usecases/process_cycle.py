from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.message_builder import build_notification
from app.domain.models import AlertEvent
from app.logging_utils import log_event
from app.repositories.state_repo import JsonStateRepository
from app.services.notifier import DoorayNotifier, NotificationError
from app.services.weather_api import WeatherAlertClient, WeatherApiError
from app.settings import Settings


@dataclass
class CycleStats:
    start_date: str
    end_date: str
    areas_processed: int = 0
    area_failures: int = 0
    alerts_fetched: int = 0
    newly_tracked: int = 0
    sent_count: int = 0
    send_failures: int = 0
    pending_total: int = 0


@dataclass
class AreaFetchResult:
    area_code: str
    area_name: str
    alerts: list[AlertEvent] | None
    error: Exception | None = None


class ProcessCycleUseCase:
    def __init__(
        self,
        settings: Settings,
        weather_client: WeatherAlertClient,
        notifier: DoorayNotifier,
        state_repo: JsonStateRepository,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.weather_client = weather_client
        self.notifier = notifier
        self.state_repo = state_repo
        self.logger = logger or logging.getLogger("weather_alert_bot.processor")

    def _fetch_alerts_for_areas(self, start_date: str, end_date: str) -> dict[str, AreaFetchResult]:
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
            log_event("cycle.parallel_fetch", workers=max_workers, area_count=area_count)
        )
        if self.settings.area_interval_sec > 0:
            self.logger.info(
                log_event(
                    "cycle.area_interval_ignored",
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
                    self.weather_client.fetch_alerts,
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

    def run_once(self, now: datetime | None = None) -> CycleStats:
        tz = ZoneInfo(self.settings.timezone)
        current = now or datetime.now(tz)
        start_base = current - timedelta(days=self.settings.lookback_days)
        start_date = start_base.strftime("%Y%m%d")
        end_date = (current + timedelta(days=1)).strftime("%Y%m%d")
        stats = CycleStats(start_date=start_date, end_date=end_date)

        self.logger.info(
            log_event(
                "cycle.start",
                start_date=start_date,
                end_date=end_date,
                area_count=len(self.settings.area_codes),
            )
        )

        area_results = self._fetch_alerts_for_areas(start_date=start_date, end_date=end_date)
        for area_code in self.settings.area_codes:
            result = area_results.get(
                area_code,
                AreaFetchResult(
                    area_code=area_code,
                    area_name=self.settings.area_code_mapping.get(area_code, "알 수 없는 지역"),
                    alerts=None,
                    error=WeatherApiError("missing_area_result"),
                ),
            )
            self.logger.info(
                log_event("area.start", area_code=area_code, area_name=result.area_name)
            )
            if result.error is not None:
                stats.area_failures += 1
                self.logger.error(
                    log_event("area.failed", area_code=area_code, error=str(result.error))
                )
                continue

            alerts = result.alerts or []
            stats.alerts_fetched += len(alerts)
            notifications = [build_notification(alert) for alert in alerts]
            for notification in notifications:
                if notification.url_validation_error:
                    self.logger.warning(
                        log_event(
                            "notification.url_attachment_blocked",
                            event_id=notification.event_id,
                            area_code=notification.area_code,
                            reason=notification.url_validation_error,
                        )
                    )
            stats.newly_tracked += self.state_repo.upsert_notifications(notifications)

            successful_event_ids: list[str] = []
            for row in self.state_repo.get_unsent(area_code=area_code):
                if self.settings.dry_run:
                    self.logger.info(
                        log_event(
                            "notification.dry_run",
                            event_id=row.event_id,
                            area_code=row.area_code,
                        )
                    )
                    continue
                try:
                    self.notifier.send(row.message, report_url=row.report_url)
                    successful_event_ids.append(row.event_id)
                except NotificationError as exc:
                    stats.send_failures += 1
                    self.logger.error(
                        log_event(
                            "notification.final_failure",
                            event_id=row.event_id,
                            area_code=row.area_code,
                            attempts=exc.attempts,
                            error=str(exc.last_error or exc),
                        )
                    )

            if successful_event_ids:
                marked_count = self.state_repo.mark_many_sent(successful_event_ids)
                stats.sent_count += marked_count
                for event_id in successful_event_ids:
                    self.logger.info(
                        log_event(
                            "notification.sent",
                            event_id=event_id,
                            area_code=area_code,
                        )
                    )

            stats.areas_processed += 1

        stats.pending_total = self.state_repo.pending_count
        return stats
