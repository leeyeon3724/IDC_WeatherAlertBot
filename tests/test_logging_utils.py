from __future__ import annotations

import json
import logging

from app.logging_utils import TimezoneFormatter, log_event, redact_sensitive_text, setup_logging


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
