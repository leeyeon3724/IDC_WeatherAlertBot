from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from app.domain.models import AlertEvent
from app.settings import (
    CANCEL_MAPPING,
    COMMAND_MAPPING,
    RESPONSE_CODE_MAPPING,
    WARN_STRESS_MAPPING,
    WARN_VAR_MAPPING,
    Settings,
)


class WeatherApiError(RuntimeError):
    """Raised when weather API fetch/parse fails."""


class WeatherAlertClient:
    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger("weather_alert_bot.weather_api")

    def fetch_alerts(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]:
        root = self._fetch_xml_root(area_code=area_code, start_date=start_date, end_date=end_date)
        return self._parse_alerts(root=root, area_code=area_code, area_name=area_name)

    def _fetch_xml_root(self, area_code: str, start_date: str, end_date: str) -> ET.Element:
        params: dict[str, str | int] = {
            "serviceKey": self.settings.service_api_key,
            "numOfRows": 100,
            "pageNo": 1,
            "fromTmFc": start_date,
            "toTmFc": end_date,
            "areaCode": area_code,
        }

        backoff_seconds = self.settings.retry_delay_sec
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                response = self.session.get(
                    self.settings.weather_alert_data_api_url,
                    params=params,
                    timeout=(
                        self.settings.request_connect_timeout_sec,
                        self.settings.request_read_timeout_sec,
                    ),
                )
                if response.status_code != 200:
                    raise WeatherApiError(f"HTTP {response.status_code}")
                return ET.fromstring(response.content)
            except (requests.RequestException, ET.ParseError, WeatherApiError) as exc:
                last_error = exc
                if attempt == self.settings.max_retries:
                    break
                self.logger.warning(
                    "weather_api.retry attempt=%s area_code=%s reason=%s backoff=%ss",
                    attempt,
                    area_code,
                    exc,
                    backoff_seconds,
                )
                time.sleep(backoff_seconds)
                backoff_seconds = max(backoff_seconds * 2, 1)

        raise WeatherApiError(f"Failed to fetch area_code={area_code}: {last_error}")

    def _parse_alerts(
        self,
        root: ET.Element,
        area_code: str,
        area_name: str,
    ) -> list[AlertEvent]:
        result_code_elem = root.find(".//resultCode")
        result_code = "N/A"
        if result_code_elem is not None and result_code_elem.text:
            result_code = result_code_elem.text.strip()
        if result_code not in {"00", "03"}:
            result_msg = RESPONSE_CODE_MAPPING.get(result_code, "알 수 없는 응답 코드")
            raise WeatherApiError(f"API response error {result_code}: {result_msg}")

        items = root.findall(".//item")
        if not items:
            return []

        alerts: list[AlertEvent] = []
        for item in items:
            warn_var_code = item.findtext("warnVar", "N/A")
            warn_stress_code = item.findtext("warnStress", "N/A")
            command_code = item.findtext("command", "N/A")
            cancel_code = item.findtext("cancel", "N/A")
            alerts.append(
                AlertEvent(
                    area_code=area_code,
                    area_name=area_name,
                    warn_var=WARN_VAR_MAPPING.get(warn_var_code, "N/A"),
                    warn_stress=WARN_STRESS_MAPPING.get(warn_stress_code, "N/A"),
                    command=COMMAND_MAPPING.get(command_code, "N/A"),
                    cancel=CANCEL_MAPPING.get(cancel_code, "N/A"),
                    start_time=self._format_datetime(item.findtext("startTime")),
                    end_time=self._format_datetime(item.findtext("endTime")),
                    stn_id=item.findtext("stnId", ""),
                    tm_fc=item.findtext("tmFc", ""),
                    tm_seq=item.findtext("tmSeq", ""),
                )
            )
        return alerts

    @staticmethod
    def _format_datetime(date_str: str | None) -> str | None:
        if not date_str or date_str == "0":
            return None
        try:
            dt = datetime.strptime(date_str, "%Y%m%d%H%M")
        except (TypeError, ValueError):
            return None

        am_pm = "오전" if dt.hour < 12 else "오후"
        hour = dt.hour % 12 or 12
        if dt.minute == 0:
            return f"{dt.year}년 {dt.month}월 {dt.day}일 {am_pm} {hour}시"
        return f"{dt.year}년 {dt.month}월 {dt.day}일 {am_pm} {hour}시 {dt.minute}분"
