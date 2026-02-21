from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

import requests

from app.domain.code_maps import (
    CANCEL_MAPPING,
    COMMAND_MAPPING,
    RESPONSE_CODE_MAPPING,
    WARN_STRESS_MAPPING,
    WARN_VAR_MAPPING,
)
from app.domain.models import AlertEvent
from app.logging_utils import log_event, redact_sensitive_text
from app.observability import events
from app.settings import Settings


class WeatherApiError(RuntimeError):
    """Raised when weather API fetch/parse fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "unknown_error",
        status_code: int | None = None,
        result_code: str | None = None,
        last_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.result_code = result_code
        self.last_error = last_error


class WeatherClient(Protocol):
    """날씨 경보 클라이언트 인터페이스.

    WeatherAlertClient와 테스트 대역(fake) 모두가 구조적으로 구현해야 하는
    최소 계약을 정의합니다. isinstance 검사 없이 병렬 조회 경로를 안전하게
    사용할 수 있도록 new_worker_client()와 close()를 포함합니다.
    """

    def fetch_alerts(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]: ...

    def new_worker_client(self) -> WeatherClient: ...

    def close(self) -> None: ...


API_ERROR_TIMEOUT: Final[str] = "timeout"
API_ERROR_CONNECTION: Final[str] = "connection"
API_ERROR_REQUEST: Final[str] = "request_error"
API_ERROR_HTTP_STATUS: Final[str] = "http_status"
API_ERROR_PARSE: Final[str] = "parse_error"
API_ERROR_RESULT: Final[str] = "api_result_error"
API_ERROR_UNKNOWN: Final[str] = "unknown_error"
DEFAULT_PAGE_SIZE: Final[int] = 100


@dataclass(frozen=True)
class WeatherApiQueryOptions:
    data_type: str = "XML"
    warning_type: str | None = None
    station_id: str | None = None


class WeatherApiRequestParamsBuilder:
    def __init__(self, options: WeatherApiQueryOptions | None = None) -> None:
        self.options = options or WeatherApiQueryOptions()

    def build(
        self,
        *,
        service_api_key: str,
        page_size: int,
        page_no: int,
        start_date: str,
        end_date: str,
        area_code: str,
    ) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "serviceKey": service_api_key,
            "numOfRows": page_size,
            "pageNo": page_no,
            "dataType": self.options.data_type,
            "fromTmFc": start_date,
            "toTmFc": end_date,
            "areaCode": area_code,
        }
        if self.options.warning_type:
            params["warningType"] = self.options.warning_type
        if self.options.station_id:
            params["stnId"] = self.options.station_id
        return params


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
        self._request_params_builder = WeatherApiRequestParamsBuilder(
            WeatherApiQueryOptions(
                warning_type=settings.weather_api_warning_type,
                station_id=settings.weather_api_station_id,
            )
        )
        self._area_name_warning_cache: set[tuple[str, str, str, str]] = set()

    def fetch_alerts(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]:
        page_no = 1
        page_size = DEFAULT_PAGE_SIZE
        total_count: int | None = None
        all_alerts: list[AlertEvent] = []
        page_count = 0

        while True:
            root = self._fetch_xml_root(
                area_code=area_code,
                start_date=start_date,
                end_date=end_date,
                page_no=page_no,
                page_size=page_size,
            )
            result_code = self._extract_result_code(root)
            if result_code == "03":
                # NODATA can be returned for out-of-range pages.
                if page_no == 1:
                    self.logger.info(
                        log_event(
                            events.AREA_FETCH_SUMMARY,
                            area_code=area_code,
                            area_name=area_name,
                            fetched_items=0,
                            page_count=1,
                            total_count=0,
                        )
                    )
                    return []
                break

            self._raise_for_result_code(result_code)
            items = root.findall(".//item")
            alerts = self._parse_items(items=items, area_code=area_code, area_name=area_name)
            all_alerts.extend(alerts)
            page_count += 1

            if total_count is None:
                total_count = self._extract_total_count(root)

            if not self._has_next_page(
                page_no=page_no,
                page_size=page_size,
                items_on_page=len(items),
                total_count=total_count,
            ):
                break
            page_no += 1

        self.logger.info(
            log_event(
                events.AREA_FETCH_SUMMARY,
                area_code=area_code,
                area_name=area_name,
                fetched_items=len(all_alerts),
                page_count=max(page_count, 1),
                total_count=total_count,
            )
        )
        return all_alerts

    def new_worker_client(self) -> WeatherAlertClient:
        return WeatherAlertClient(settings=self.settings, logger=self.logger)

    def close(self) -> None:
        self.session.close()

    def _fetch_xml_root(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        *,
        page_no: int,
        page_size: int,
    ) -> ET.Element:
        params = self._request_params_builder.build(
            service_api_key=self.settings.service_api_key,
            page_size=page_size,
            page_no=page_no,
            start_date=start_date,
            end_date=end_date,
            area_code=area_code,
        )

        backoff_seconds = self.settings.retry_delay_sec
        last_error: WeatherApiError | None = None
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
                    raise WeatherApiError(
                        f"HTTP {response.status_code}",
                        code=API_ERROR_HTTP_STATUS,
                        status_code=response.status_code,
                    )
                return ET.fromstring(response.content)
            except requests.RequestException as exc:
                last_error = WeatherApiError(
                    f"Request failed: {exc}",
                    code=self._classify_request_exception(exc),
                    last_error=exc,
                )
            except ET.ParseError as exc:
                last_error = WeatherApiError(
                    f"Failed to parse XML: {exc}",
                    code=API_ERROR_PARSE,
                    last_error=exc,
                )
            except WeatherApiError as exc:
                last_error = exc

            if last_error is not None:
                if attempt == self.settings.max_retries:
                    break
                self.logger.warning(
                    log_event(
                        events.AREA_FETCH_RETRY,
                        attempt=attempt,
                        max_retries=self.settings.max_retries,
                        area_code=area_code,
                        error_code=last_error.code,
                        error=redact_sensitive_text(last_error),
                        backoff_sec=backoff_seconds,
                    )
                )
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
                backoff_seconds = max(backoff_seconds * 2, self.settings.retry_delay_sec)

        if last_error is not None:
            raise WeatherApiError(
                f"Failed to fetch area_code={area_code}: {last_error}",
                code=last_error.code,
                status_code=last_error.status_code,
                result_code=last_error.result_code,
                last_error=last_error.last_error or last_error,
            )
        raise WeatherApiError(
            f"Failed to fetch area_code={area_code}: unknown",
            code=API_ERROR_UNKNOWN,
        )

    def _parse_items(
        self,
        items: list[ET.Element],
        *,
        area_code: str,
        area_name: str,
    ) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []
        for item in items:
            response_area_name = (item.findtext("areaName", "") or "").strip()
            resolved_area_name = self._resolve_area_name(
                area_code=area_code,
                configured_area_name=area_name,
                response_area_name=response_area_name,
            )
            warn_var_code = item.findtext("warnVar", "N/A")
            warn_stress_code = item.findtext("warnStress", "N/A")
            command_code = item.findtext("command", "N/A")
            cancel_code = item.findtext("cancel", "N/A")
            alerts.append(
                AlertEvent(
                    area_code=area_code,
                    area_name=resolved_area_name,
                    warn_var=self._resolve_code_mapping(
                        field_name="warnVar",
                        raw_code=warn_var_code,
                        mapping=WARN_VAR_MAPPING,
                        area_code=area_code,
                        area_name=area_name,
                    ),
                    warn_stress=self._resolve_code_mapping(
                        field_name="warnStress",
                        raw_code=warn_stress_code,
                        mapping=WARN_STRESS_MAPPING,
                        area_code=area_code,
                        area_name=area_name,
                    ),
                    command=self._resolve_code_mapping(
                        field_name="command",
                        raw_code=command_code,
                        mapping=COMMAND_MAPPING,
                        area_code=area_code,
                        area_name=area_name,
                    ),
                    cancel=self._resolve_code_mapping(
                        field_name="cancel",
                        raw_code=cancel_code,
                        mapping=CANCEL_MAPPING,
                        area_code=area_code,
                        area_name=area_name,
                    ),
                    start_time=self._format_datetime(item.findtext("startTime")),
                    end_time=self._format_datetime(item.findtext("endTime")),
                    stn_id=item.findtext("stnId", ""),
                    tm_fc=item.findtext("tmFc", ""),
                    tm_seq=item.findtext("tmSeq", ""),
                )
            )
        return alerts

    def _resolve_area_name(
        self,
        *,
        area_code: str,
        configured_area_name: str,
        response_area_name: str,
    ) -> str:
        configured = configured_area_name.strip()
        response = response_area_name.strip()

        has_configured = bool(configured and configured != "알 수 없는 지역")
        has_response = bool(response)

        if has_configured:
            if has_response and configured != response:
                self._log_area_name_mapping_warning(
                    area_code=area_code,
                    reason="mismatch",
                    configured_area_name=configured,
                    response_area_name=response,
                    resolved_area_name=configured,
                )
            return configured

        if has_response:
            self._log_area_name_mapping_warning(
                area_code=area_code,
                reason="missing_mapping",
                configured_area_name=configured or None,
                response_area_name=response,
                resolved_area_name=response,
            )
            return response

        self._log_area_name_mapping_warning(
            area_code=area_code,
            reason="missing_mapping_and_response",
            configured_area_name=configured or None,
            response_area_name=None,
            resolved_area_name=area_code,
        )
        return area_code

    def _log_area_name_mapping_warning(
        self,
        *,
        area_code: str,
        reason: str,
        configured_area_name: str | None,
        response_area_name: str | None,
        resolved_area_name: str,
    ) -> None:
        cache_key = (
            area_code,
            reason,
            configured_area_name or "",
            response_area_name or "",
        )
        if cache_key in self._area_name_warning_cache:
            return
        self._area_name_warning_cache.add(cache_key)
        self.logger.warning(
            log_event(
                events.AREA_NAME_MAPPING_WARNING,
                area_code=area_code,
                reason=reason,
                configured_area_name=configured_area_name,
                response_area_name=response_area_name,
                resolved_area_name=resolved_area_name,
            )
        )

    def _resolve_code_mapping(
        self,
        *,
        field_name: str,
        raw_code: str,
        mapping: dict[str, str],
        area_code: str,
        area_name: str,
    ) -> str:
        normalized_code = (raw_code or "").strip()
        if not normalized_code:
            return "N/A"

        mapped_value = mapping.get(normalized_code)
        if mapped_value is not None:
            return mapped_value

        if normalized_code.upper() == "N/A":
            return "N/A"

        fallback_value = f"UNKNOWN({field_name}:{normalized_code})"
        self.logger.warning(
            log_event(
                events.AREA_CODE_UNMAPPED,
                area_code=area_code,
                area_name=area_name,
                field=field_name,
                raw_code=normalized_code,
                fallback_value=fallback_value,
            )
        )
        return fallback_value

    @staticmethod
    def _extract_result_code(root: ET.Element) -> str:
        result_code_elem = root.find(".//resultCode")
        if result_code_elem is None or not result_code_elem.text:
            return "N/A"
        result_code = result_code_elem.text.strip()
        if result_code.isdigit() and len(result_code) <= 2:
            return result_code.zfill(2)
        return result_code

    @staticmethod
    def _extract_total_count(root: ET.Element) -> int | None:
        total_count_text = root.findtext(".//totalCount")
        if not total_count_text:
            return None
        try:
            value = int(total_count_text.strip())
        except ValueError:
            return None
        return max(value, 0)

    @staticmethod
    def _has_next_page(
        *,
        page_no: int,
        page_size: int,
        items_on_page: int,
        total_count: int | None,
    ) -> bool:
        if items_on_page <= 0:
            return False
        if total_count is not None:
            return page_no * page_size < total_count
        return items_on_page >= page_size

    @staticmethod
    def _raise_for_result_code(result_code: str) -> None:
        if result_code in {"00", "03"}:
            return
        result_msg = RESPONSE_CODE_MAPPING.get(result_code, "알 수 없는 응답 코드")
        raise WeatherApiError(
            f"API response error {result_code}: {result_msg}",
            code=API_ERROR_RESULT,
            result_code=result_code,
        )

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

    @staticmethod
    def _classify_request_exception(exc: requests.RequestException) -> str:
        if isinstance(exc, requests.Timeout):
            return API_ERROR_TIMEOUT
        if isinstance(exc, requests.ConnectionError):
            return API_ERROR_CONNECTION
        return API_ERROR_REQUEST
