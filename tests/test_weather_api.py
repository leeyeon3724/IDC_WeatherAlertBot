from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest
import requests

from app.domain.alert_rules import default_alert_rules
from app.observability import events
from app.services.weather_api import (
    API_ERROR_CONNECTION,
    API_ERROR_HTTP_STATUS,
    API_ERROR_PARSE,
    API_ERROR_REQUEST,
    API_ERROR_RESULT,
    API_ERROR_TIMEOUT,
    API_ERROR_UNKNOWN,
    API_ERROR_UNMAPPED_CODE,
    WeatherAlertClient,
    WeatherApiError,
)
from app.settings import Settings


class DummyResponse:
    def __init__(
        self,
        status_code: int,
        content: bytes,
        *,
        encoding: str | None = "utf-8",
        apparent_encoding: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.encoding = encoding
        self.apparent_encoding = apparent_encoding


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


def _settings(
    tmp_path,
    *,
    max_retries: int = 2,
    retry_delay_sec: int = 0,
    **overrides: object,
) -> Settings:
    base: dict[str, object] = {
        "service_api_key": "test-key",
        "service_hook_url": "https://hook.example",
        "weather_alert_data_api_url": "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd",
        "sent_messages_file": tmp_path / "state.json",
        "area_codes": ["L1070100"],
        "area_code_mapping": {"L1070100": "대구"},
        "request_timeout_sec": 1,
        "request_connect_timeout_sec": 2,
        "request_read_timeout_sec": 3,
        "max_retries": max_retries,
        "retry_delay_sec": retry_delay_sec,
        "api_soft_rate_limit_per_sec": 0,
        "notifier_timeout_sec": 1,
        "notifier_connect_timeout_sec": 1,
        "notifier_read_timeout_sec": 1,
        "notifier_max_retries": 1,
        "notifier_retry_delay_sec": 0,
        "area_max_workers": 1,
        "lookback_days": 0,
        "cycle_interval_sec": 0,
        "area_interval_sec": 0,
        "cleanup_enabled": False,
        "cleanup_retention_days": 30,
        "cleanup_include_unsent": True,
        "bot_name": "테스트봇",
        "timezone": "Asia/Seoul",
        "log_level": "INFO",
        "dry_run": True,
        "run_once": True,
    }
    base.update(overrides)
    return Settings(**base)


def _xml_with_item(
    *,
    result_code: str = "00",
    warn_var: str = "4",
    warn_stress: str = "0",
    command: str = "2",
    cancel: str = "0",
    area_name: str | None = "예제구역",
    start_time: str = "202602181000",
    total_count: int | None = None,
    tm_seq: str = "46",
) -> bytes:
    total_count_part = f"<totalCount>{total_count}</totalCount>" if total_count is not None else ""
    area_name_part = f"<areaName>{area_name}</areaName>" if area_name is not None else ""
    return f"""
    <response>
      <header><resultCode>{result_code}</resultCode></header>
      <body>
        {total_count_part}
        <items>
          <item>
            {area_name_part}
            <warnVar>{warn_var}</warnVar>
            <warnStress>{warn_stress}</warnStress>
            <command>{command}</command>
            <cancel>{cancel}</cancel>
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
    assert session.calls[0][0] == "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd"
    assert session.calls[0][2] == (2, 3)
    assert session.calls[0][1]["dataType"] == "XML"


def test_fetch_alerts_includes_optional_weather_filter_params(tmp_path) -> None:
    session = FakeSession([DummyResponse(200, _xml_with_item())])
    client = WeatherAlertClient(
        settings=_settings(
            tmp_path,
            weather_api_warning_type="6",
            weather_api_station_id="108",
        ),
        session=session,
        logger=logging.getLogger("test.weather.api.filter_params"),
    )

    client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    params = session.calls[0][1]
    assert params["warningType"] == "6"
    assert params["stnId"] == "108"
    assert params["dataType"] == "XML"


def test_new_worker_client_creates_isolated_session(tmp_path) -> None:
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        logger=logging.getLogger("test.weather.api.worker"),
    )
    worker_client = client.new_worker_client()

    try:
        assert worker_client is not client
        assert worker_client.settings is client.settings
        assert worker_client.logger is client.logger
        assert worker_client.session is not client.session
        assert worker_client._request_rate_limiter is client._request_rate_limiter
    finally:
        client.session.close()
        worker_client.session.close()


def test_fetch_alerts_soft_rate_limit_applies_between_requests(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            DummyResponse(200, _xml_with_item(total_count=101, tm_seq="1")),
            DummyResponse(200, _xml_with_item(total_count=101, tm_seq="2")),
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(
            tmp_path,
            max_retries=1,
            retry_delay_sec=0,
            api_soft_rate_limit_per_sec=2,
        ),
        session=session,
        logger=logging.getLogger("test.weather.api.soft_rate_limit"),
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr("app.services.weather_api.time.monotonic", lambda: 0.0)
    monkeypatch.setattr("app.services.weather_api.time.sleep", lambda sec: sleep_calls.append(sec))

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert len(alerts) == 2
    assert len(session.calls) == 2
    assert sleep_calls == [0.5]


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


def test_fetch_alerts_retries_on_result_code_22_then_succeeds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                b"<response><header><resultCode>22</resultCode></header></response>",
            ),
            DummyResponse(200, _xml_with_item()),
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=2, retry_delay_sec=1),
        session=session,
        logger=logging.getLogger("test.weather.api.retry.result_code_22.success"),
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


def test_fetch_alerts_raises_when_result_code_22_retries_exhausted(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                b"<response><header><resultCode>22</resultCode></header></response>",
            ),
            DummyResponse(
                200,
                b"<response><header><resultCode>22</resultCode></header></response>",
            ),
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=2, retry_delay_sec=1),
        session=session,
        logger=logging.getLogger("test.weather.api.retry.result_code_22.fail"),
    )
    sleep_calls: list[int] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    with pytest.raises(WeatherApiError, match="API response error 22") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )

    assert exc_info.value.code == API_ERROR_RESULT
    assert exc_info.value.result_code == "22"
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


def test_fetch_alerts_stops_when_next_page_returns_nodata(tmp_path) -> None:
    session = FakeSession(
        [
            DummyResponse(200, _xml_with_item(total_count=101, tm_seq="1")),
            DummyResponse(
                200,
                b"<response><header><resultCode>03</resultCode></header></response>",
            ),
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logging.getLogger("test.weather.api.pagination.nodata"),
    )

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert len(alerts) == 1
    assert alerts[0].tm_seq == "1"
    assert len(session.calls) == 2


def test_fetch_alerts_returns_empty_when_first_page_is_nodata(tmp_path) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                b"<response><header><resultCode>03</resultCode></header></response>",
            )
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logging.getLogger("test.weather.api.first.nodata"),
    )

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert alerts == []
    assert len(session.calls) == 1


def test_fetch_alerts_accepts_single_digit_zero_result_code(tmp_path) -> None:
    session = FakeSession([DummyResponse(200, _xml_with_item(result_code="0"))])
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logging.getLogger("test.weather.api.single_digit_result_code"),
    )

    alerts = client.fetch_alerts(
        area_code="L1070100",
        start_date="20260218",
        end_date="20260219",
        area_name="대구",
    )

    assert len(alerts) == 1
    assert alerts[0].warn_var == "건조"


def test_fetch_alerts_logs_unmapped_codes_with_fallback_values(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                _xml_with_item(warn_var="99", warn_stress="7", command="9", cancel="9"),
            )
        ]
    )
    logger = logging.getLogger("test.weather.api.unmapped_codes")
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=1, retry_delay_sec=0),
        session=session,
        logger=logger,
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        alerts = client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )

    assert len(alerts) == 1
    assert alerts[0].warn_var == "99"
    assert alerts[0].warn_stress == "7"
    assert alerts[0].command == "9"
    assert alerts[0].cancel == "9"

    warning_payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert any(
        payload.get("event") == events.AREA_CODE_UNMAPPED
        and payload.get("field") == "warnVar"
        and payload.get("raw_code") == "99"
        for payload in warning_payloads
    )


def test_fetch_alerts_fail_fast_when_unmapped_policy_is_fail(tmp_path) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                _xml_with_item(warn_var="99", warn_stress="7", command="9", cancel="9"),
            )
        ]
    )
    fail_fast_rules = replace(default_alert_rules(), unmapped_code_policy="fail")
    client = WeatherAlertClient(
        settings=_settings(
            tmp_path,
            max_retries=1,
            retry_delay_sec=0,
            alert_rules=fail_fast_rules,
        ),
        session=session,
        logger=logging.getLogger("test.weather.api.unmapped_codes.fail_fast"),
    )

    with pytest.raises(WeatherApiError, match="Unmapped code") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )
    assert exc_info.value.code == API_ERROR_UNMAPPED_CODE


def test_fetch_alerts_uses_response_area_name_when_mapping_missing(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession([DummyResponse(200, _xml_with_item(area_name="남해서부동쪽먼바다"))])
    logger = logging.getLogger("test.weather.api.area_name.missing_mapping")
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logger,
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        alerts = client.fetch_alerts(
            area_code="S1322200",
            start_date="20260218",
            end_date="20260219",
            area_name="알 수 없는 지역",
        )

    assert len(alerts) == 1
    assert alerts[0].area_name == "남해서부동쪽먼바다"
    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(
        payload.get("event") == events.AREA_NAME_MAPPING_WARNING
        and payload.get("reason") == "missing_mapping"
        and payload.get("resolved_area_name") == "남해서부동쪽먼바다"
        for payload in payloads
    )


def test_fetch_alerts_prefers_configured_area_name_on_mismatch(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession([DummyResponse(200, _xml_with_item(area_name="남해서부동쪽먼바다"))])
    logger = logging.getLogger("test.weather.api.area_name.mismatch")
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logger,
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        alerts = client.fetch_alerts(
            area_code="S1322200",
            start_date="20260218",
            end_date="20260219",
            area_name="설정지역명",
        )

    assert len(alerts) == 1
    assert alerts[0].area_name == "설정지역명"
    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(
        payload.get("event") == events.AREA_NAME_MAPPING_WARNING
        and payload.get("reason") == "mismatch"
        and payload.get("configured_area_name") == "설정지역명"
        and payload.get("response_area_name") == "남해서부동쪽먼바다"
        for payload in payloads
    )


def test_fetch_alerts_falls_back_to_area_code_when_names_are_missing(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession([DummyResponse(200, _xml_with_item(area_name=None))])
    logger = logging.getLogger("test.weather.api.area_name.area_code_fallback")
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=session,
        logger=logger,
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        alerts = client.fetch_alerts(
            area_code="S1322200",
            start_date="20260218",
            end_date="20260219",
            area_name="알 수 없는 지역",
        )

    assert len(alerts) == 1
    assert alerts[0].area_name == "S1322200"
    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(
        payload.get("event") == events.AREA_NAME_MAPPING_WARNING
        and payload.get("reason") == "missing_mapping_and_response"
        and payload.get("resolved_area_name") == "S1322200"
        for payload in payloads
    )


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


def test_fetch_alerts_raises_http_status_error(tmp_path) -> None:
    session = FakeSession([DummyResponse(500, b"<response/>")])
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=1, retry_delay_sec=0),
        session=session,
        logger=logging.getLogger("test.weather.api.http_status"),
    )

    with pytest.raises(WeatherApiError, match="Failed to fetch area_code=L1070100") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )
    assert exc_info.value.code == API_ERROR_HTTP_STATUS
    assert exc_info.value.status_code == 500


def test_fetch_alerts_raises_parse_error_for_invalid_xml(tmp_path) -> None:
    session = FakeSession([DummyResponse(200, b"<response><broken>")])
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=1, retry_delay_sec=0),
        session=session,
        logger=logging.getLogger("test.weather.api.parse.invalid_xml"),
    )

    with pytest.raises(WeatherApiError, match="Failed to fetch area_code=L1070100") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )
    assert exc_info.value.code == API_ERROR_PARSE


def test_fetch_alerts_raises_parse_error_when_result_code_tag_is_missing(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession([DummyResponse(200, b"<response><header></header></response>")])
    logger = logging.getLogger("test.weather.api.parse.missing_result_code")
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=1, retry_delay_sec=0),
        session=session,
        logger=logger,
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        with pytest.raises(WeatherApiError, match="resultCode") as exc_info:
            client.fetch_alerts(
                area_code="L1070100",
                start_date="20260218",
                end_date="20260219",
                area_name="대구",
            )

    assert exc_info.value.code == API_ERROR_PARSE
    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(
        payload.get("event") == events.AREA_FAILED
        and payload.get("area_code") == "L1070100"
        and payload.get("error_code") == API_ERROR_PARSE
        for payload in payloads
    )


def test_fetch_alerts_raises_parse_error_when_required_item_tag_missing(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                """
                <response>
                  <header><resultCode>00</resultCode></header>
                  <body>
                    <items>
                      <item>
                        <areaName>예제구역</areaName>
                        <warnStress>0</warnStress>
                        <command>2</command>
                        <cancel>0</cancel>
                        <startTime>202602181000</startTime>
                        <endTime>0</endTime>
                        <stnId>143</stnId>
                        <tmFc>202602181000</tmFc>
                        <tmSeq>46</tmSeq>
                      </item>
                    </items>
                  </body>
                </response>
                """.encode(),
            )
        ]
    )
    logger = logging.getLogger("test.weather.api.parse.missing_item_tag")
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=1, retry_delay_sec=0),
        session=session,
        logger=logger,
    )

    with caplog.at_level(logging.ERROR, logger=logger.name):
        with pytest.raises(WeatherApiError, match="warnVar") as exc_info:
            client.fetch_alerts(
                area_code="L1070100",
                start_date="20260218",
                end_date="20260219",
                area_name="대구",
            )

    assert exc_info.value.code == API_ERROR_PARSE
    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(
        payload.get("event") == events.AREA_FAILED
        and payload.get("area_code") == "L1070100"
        and payload.get("error_code") == API_ERROR_PARSE
        for payload in payloads
    )


def test_fetch_alerts_raises_result_code_error_in_integration_path(tmp_path) -> None:
    session = FakeSession(
        [
            DummyResponse(
                200,
                b"<response><header><resultCode>10</resultCode></header></response>",
            )
        ]
    )
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=1, retry_delay_sec=0),
        session=session,
        logger=logging.getLogger("test.weather.api.result_code"),
    )

    with pytest.raises(WeatherApiError, match="API response error 10") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )
    assert exc_info.value.code == API_ERROR_RESULT
    assert exc_info.value.result_code == "10"


def test_fetch_alerts_raises_unknown_when_retry_loop_is_skipped(tmp_path) -> None:
    session = FakeSession([])
    client = WeatherAlertClient(
        settings=_settings(tmp_path, max_retries=0, retry_delay_sec=0),
        session=session,
        logger=logging.getLogger("test.weather.api.unknown"),
    )

    with pytest.raises(WeatherApiError, match="unknown") as exc_info:
        client.fetch_alerts(
            area_code="L1070100",
            start_date="20260218",
            end_date="20260219",
            area_name="대구",
        )
    assert exc_info.value.code == API_ERROR_UNKNOWN
    assert session.calls == []


def test_raise_for_result_code_raises_for_error_result_code(tmp_path) -> None:
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=FakeSession([]),
        logger=logging.getLogger("test.weather.api.result_code.raise"),
    )
    with pytest.raises(WeatherApiError, match="API response error 10") as exc_info:
        client._raise_for_result_code("10")
    assert exc_info.value.code == API_ERROR_RESULT


def test_raise_for_result_code_returns_for_no_data(tmp_path) -> None:
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=FakeSession([]),
        logger=logging.getLogger("test.weather.api.result_code.no_data"),
    )
    client._raise_for_result_code("03")


def test_parse_items_returns_alert_events(tmp_path) -> None:
    root = ET.fromstring(_xml_with_item(result_code="00"))
    items = root.findall(".//item")
    client = WeatherAlertClient(
        settings=_settings(tmp_path),
        session=FakeSession([]),
        logger=logging.getLogger("test.weather.api.parse.items"),
    )

    alerts = client._parse_items(items=items, area_code="L1070100", area_name="대구")
    assert len(alerts) == 1
    assert alerts[0].tm_seq == "46"


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
    assert (
        WeatherAlertClient._classify_request_exception(requests.RequestException("request"))
        == API_ERROR_REQUEST
    )


def test_extract_total_count_invalid_returns_none() -> None:
    root = ET.fromstring(
        """
        <response>
          <header><resultCode>00</resultCode></header>
          <body><totalCount>not-a-number</totalCount></body>
        </response>
        """
    )
    assert WeatherAlertClient._extract_total_count(root) is None


def test_extract_total_count_negative_clamps_to_zero() -> None:
    root = ET.fromstring(
        """
        <response>
          <header><resultCode>00</resultCode></header>
          <body><totalCount>-10</totalCount></body>
        </response>
        """
    )
    assert WeatherAlertClient._extract_total_count(root) == 0


def test_extract_result_code_missing_returns_na() -> None:
    root = ET.fromstring("<response><header></header></response>")
    with pytest.raises(WeatherApiError, match="resultCode") as exc_info:
        WeatherAlertClient._extract_result_code(root, area_code="L1070100", page_no=1)
    assert exc_info.value.code == API_ERROR_PARSE


def test_extract_result_code_normalizes_single_digit_numeric() -> None:
    root = ET.fromstring("<response><header><resultCode>3</resultCode></header></response>")
    assert (
        WeatherAlertClient._extract_result_code(root, area_code="L1070100", page_no=1) == "03"
    )


@pytest.mark.parametrize(
    ("page_no", "page_size", "items_on_page", "total_count", "expected"),
    [
        (1, 100, 0, None, False),
        (1, 100, 100, 100, False),
        (1, 100, 100, 101, True),
        (2, 100, 50, None, False),
    ],
)
def test_has_next_page_boundaries(
    page_no: int,
    page_size: int,
    items_on_page: int,
    total_count: int | None,
    expected: bool,
) -> None:
    assert (
        WeatherAlertClient._has_next_page(
            page_no=page_no,
            page_size=page_size,
            items_on_page=items_on_page,
            total_count=total_count,
        )
        is expected
    )
