from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.logging_utils import TimezoneFormatter, log_event, redact_sensitive_text, setup_logging
from app.observability import events
from app.repositories.json_state_repo import JsonStateRepository


@pytest.fixture(autouse=True)
def _restore_weather_alert_bot_logger() -> None:
    logger = logging.getLogger("weather_alert_bot")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    yield
    current_handlers = list(logger.handlers)
    for handler in current_handlers:
        logger.removeHandler(handler)
        if handler not in original_handlers:
            try:
                handler.close()
            except Exception:
                pass
    for handler in original_handlers:
        logger.addHandler(handler)
    logger.setLevel(original_level)
    logger.propagate = original_propagate


def _reset_logger() -> logging.Logger:
    logger = logging.getLogger("weather_alert_bot")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    return logger


def test_setup_logging_adds_handler_when_empty() -> None:
    logger = _reset_logger()
    configured = setup_logging(log_level="debug", timezone="Asia/Seoul")

    assert configured is logger
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    formatter = logger.handlers[0].formatter
    assert isinstance(formatter, TimezoneFormatter)
    assert formatter.tz.key == "Asia/Seoul"
    assert logger.propagate is False


def test_setup_logging_updates_existing_timezone_formatter() -> None:
    logger = _reset_logger()
    setup_logging(log_level="info", timezone="Asia/Seoul")

    configured = setup_logging(log_level="warning", timezone="UTC")

    assert configured is logger
    assert logger.level == logging.WARNING
    formatter = logger.handlers[0].formatter
    assert isinstance(formatter, TimezoneFormatter)
    assert formatter.tz.key == "UTC"


def test_setup_logging_keeps_non_timezone_handlers() -> None:
    logger = _reset_logger()
    plain_handler = logging.StreamHandler()
    plain_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(plain_handler)

    setup_logging(log_level="info", timezone="UTC")

    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, logging.Formatter)
    assert not isinstance(logger.handlers[0].formatter, TimezoneFormatter)


def test_log_event_serializes_fields() -> None:
    payload = log_event("cycle.start", area_code="L1070100", area_name="대구")
    decoded = json.loads(payload)
    assert decoded["event"] == "cycle.start"
    assert decoded["area_code"] == "L1070100"
    assert decoded["area_name"] == "대구"


def test_redact_sensitive_text_masks_key_patterns() -> None:
    text = (
        "GET /weather?serviceKey=ABCD1234&apiKey=XYZ987 "
        "SERVICE_API_KEY=PLAIN_VALUE"
    )

    redacted = redact_sensitive_text(text)

    assert "ABCD1234" not in redacted
    assert "XYZ987" not in redacted
    assert "PLAIN_VALUE" not in redacted
    assert "serviceKey=***" in redacted
    assert "apiKey=***" in redacted
    assert "SERVICE_API_KEY=***" in redacted


def test_redact_sensitive_text_masks_dooray_webhook_url() -> None:
    """웹훅 URL(Dooray /services/... 경로)이 로그에서 마스킹되어야 한다."""
    text = (
        "POST failed for https://hook.dooray.com/services/12345/abcdef/TOKEN123 "
        "with status 500"
    )

    redacted = redact_sensitive_text(text)

    assert "TOKEN123" not in redacted
    assert "12345" not in redacted
    assert "https://***" in redacted


def test_setup_logging_does_not_break_following_caplog_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("{}", encoding="utf-8")
    original_open = Path.open

    def _failing_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        if self == state_file and "r" in mode:
            raise OSError("read failed")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _failing_open)
    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.state"):
        JsonStateRepository(state_file)

    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(payload.get("event") == events.STATE_READ_FAILED for payload in payloads)
