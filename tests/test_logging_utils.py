from __future__ import annotations

import json
import logging

from app.logging_utils import TimezoneFormatter, log_event, setup_logging


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
