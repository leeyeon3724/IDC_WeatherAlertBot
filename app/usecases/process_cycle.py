from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.message_builder import build_notification
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

    def run_once(self, now: datetime | None = None) -> CycleStats:
        tz = ZoneInfo(self.settings.timezone)
        current = now or datetime.now(tz)
        start_date = current.strftime("%Y%m%d")
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

        last_index = len(self.settings.area_codes) - 1
        for idx, area_code in enumerate(self.settings.area_codes):
            area_name = self.settings.area_code_mapping.get(area_code, "알 수 없는 지역")
            self.logger.info(
                log_event("area.start", area_code=area_code, area_name=area_name)
            )
            try:
                alerts = self.weather_client.fetch_alerts(
                    area_code=area_code,
                    start_date=start_date,
                    end_date=end_date,
                    area_name=area_name,
                )
                stats.alerts_fetched += len(alerts)
                notifications = [build_notification(alert) for alert in alerts]
                stats.newly_tracked += self.state_repo.upsert_notifications(notifications)

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
                        self.state_repo.mark_sent(row.event_id)
                        stats.sent_count += 1
                        self.logger.info(
                            log_event(
                                "notification.sent",
                                event_id=row.event_id,
                                area_code=row.area_code,
                            )
                        )
                    except NotificationError as exc:
                        stats.send_failures += 1
                        self.logger.error(
                            log_event(
                                "notification.failed",
                                event_id=row.event_id,
                                area_code=row.area_code,
                                error=str(exc),
                            )
                        )
                stats.areas_processed += 1
            except WeatherApiError as exc:
                stats.area_failures += 1
                self.logger.error(
                    log_event("area.failed", area_code=area_code, error=str(exc))
                )
            finally:
                if idx < last_index and self.settings.area_interval_sec > 0:
                    time.sleep(self.settings.area_interval_sec)

        stats.pending_total = self.state_repo.pending_count
        return stats
