from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import pytest
import requests

from app.services.weather_api import (
    API_ERROR_CONNECTION,
    API_ERROR_RESULT,
    API_ERROR_TIMEOUT,
    WeatherAlertClient,
    WeatherApiError,
)
from app.settings import Settings


class DummyResponse:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content


class FakeSession:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, object, object]] = []

    def get(self, url: str, params: object = None, timeout: object = None) -> DummyResponse:
        self.calls.append((url, params, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _settings(tmp_path, *, max_retries: int = 2, retry_delay_sec: int = 0) -> Settings:
    return Settings(
        service_api_key="test-key",
        service_hook_url="https://hook.example",
        weather_alert_data_api_url="https://api.example/weather",
        sent_messages_file=tmp_path / "state.json",
        area_codes=["L1070100"],
        area_code_mapping={"L1070100": "대구"},
        request_timeout_sec=1,
        request_connect_timeout_sec=2,
        request_read_timeout_sec=3,
        max_retries=max_retries,
        retry_delay_sec=retry_delay_sec,
        notifier_timeout_sec=1,
        notifier_connect_timeout_sec=1,
        notifier_read_timeout_sec=1,
        notifier_max_retries=1,
        notifier_retry_delay_sec=0,
        area_max_workers=1,
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


def _xml_with_item(
    *,
    result_code: str = "00",
    warn_var: str = "4",
    start_time: str = "202602181000",
    total_count: int | None = None,
    tm_seq: str = "46",
) -> bytes:
    total_count_part = f"<totalCount>{total_count}</totalCount>" if total_count is not None else ""
    return f"""
    <response>
      <header><resultCode>{result_code}</resultCode></header>
      <body>
        {total_count_part}
        <items>
          <item>
            <warnVar>{warn_var}</warnVar>
            <warnStress>0</warnStress>
            <command>2</command>
            <cancel>0</cancel>
            <startTime>{start_time}</startTime>
            <endTime>0</endTime>
            <stnId>143</stnId>
            <tmFc>202602181000</tmFc>
            <tmSeq>{tm_seq}</tmSeq>
          </item>
        </items>
      </body>
    </response>
    """.encode()


def test_fetch_alerts_success(tmp_path) -> None:
    session = FakeSession([DummyResponse(200, _xml_with_item())])
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logging.getLogger("test.weather.api.success"),
    )

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert len(alerts) == 1
    assert alerts[0].warn_var == "건조"
    assert alerts[0].warn_stress == "주의보"
    assert alerts[0].command == "해제"
    assert alerts[0].cancel == "정상"
    assert alerts[0].start_time == "2026년 2월 18일 오전 10시"
    assert alerts[0].end_time is None
    assert alerts[0].stn_id == "143"
    assert session.calls[0][0] == "https://api.example/weather"
    assert session.calls[0][2] == (2, 3)


def test_fetch_alerts_retries_then_succeeds(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            requests.Timeout("temporary timeout"),
            DummyResponse(200, _xml_with_item()),
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=2, retry_delay_sec=1),
        session=session,
        logger=logging.getLogger("test.weather.api.retry"),
    )
    sleep_calls: list[int] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert len(alerts) == 1
    assert len(session.calls) == 2
    assert sleep_calls == [1]


def test_fetch_alerts_supports_pagination(tmp_path) -> None:
    session = FakeSession(
        [
            DummyResponse(200, _xml_with_item(total_count=101, tm_seq="1")),
            DummyResponse(200, _xml_with_item(total_count=101, tm_seq="2")),
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logging.getLogger("test.weather.api.pagination"),
    )

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert len(alerts) == 2
    assert alerts[0].tm_seq == "1"
    assert alerts[1].tm_seq == "2"
    assert len(session.calls) == 2
    assert session.calls[0][1]["pageNo"] == 1
    assert session.calls[1][1]["pageNo"] == 2


def test_fetch_alerts_raises_after_max_retries(tmp_path) -> None:
    session = FakeSession([requests.Timeout("t1"), requests.Timeout("t2")])
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=2, retry_delay_sec=0),
        session=session,
        logger=logging.getLogger("test.weather.api.fail"),
    )

    with pytest.raises(WeatherApiError, match="Failed to fetch area_code=L1070100") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )
    assert exc_info.value.code == API_ERROR_TIMEOUT


def test_parse_alerts_raises_for_error_result_code(tmp_path) -> None:
    root = ET.fromstring("<response><header><resultCode>10</resultCode></header></response>")
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=FakeSession([]),
        logger=logging.getLogger("test.weather.api.parse.error"),
    )

    with pytest.raises(WeatherApiError, match="API response error 10") as exc_info:
        client._parse_alerts(root=root, area_code="L1070100", area_name="대구")
    assert exc_info.value.code == API_ERROR_RESULT


def test_parse_alerts_handles_no_data_result(tmp_path) -> None:
    root = ET.fromstring("<response><header><resultCode>03</resultCode></header></response>")
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=FakeSession([]),
        logger=logging.getLogger("test.weather.api.parse.empty"),
    )

    assert client._parse_alerts(root=root, area_code="L1070100", area_name="대구") == []


def test_format_datetime_variants() -> None:
    assert WeatherAlertClient._format_datetime(None) is None
    assert WeatherAlertClient._format_datetime("0") is None
    assert WeatherAlertClient._format_datetime("invalid") is None
    assert WeatherAlertClient._format_datetime("202602181000") == "2026년 2월 18일 오전 10시"
    assert WeatherAlertClient._format_datetime("202602181030") == "2026년 2월 18일 오전 10시 30분"


def test_classify_request_exception() -> None:
    assert (
        WeatherAlertClient._classify_request_exception(requests.Timeout("timeout"))
        == API_ERROR_TIMEOUT
    )
    assert (
        WeatherAlertClient._classify_request_exception(requests.ConnectionError("conn"))
        == API_ERROR_CONNECTION
    )
