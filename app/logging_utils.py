from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo


class TimezoneFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
        validate: bool = True,
        *,
        defaults: dict[str, Any] | None = None,
        tz_name: str = "Asia/Seoul",
    ) -> None:
        super().__init__(
            fmt=fmt,
            datefmt=datefmt,
            style=style,
            validate=validate,
            defaults=defaults,
        )
        self.tz = ZoneInfo(tz_name)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def setup_logging(log_level: str = "INFO", timezone: str = "Asia/Seoul") -> logging.Logger:
    logger = logging.getLogger("weather_alert_bot")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        for handler in logger.handlers:
            if isinstance(handler.formatter, TimezoneFormatter):
                handler.setFormatter(
                    TimezoneFormatter(
                        fmt="[%(asctime)s] [%(levelname)s] %(name)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                        tz_name=timezone,
                    )
                )
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(
        TimezoneFormatter(
            fmt="[%(asctime)s] [%(levelname)s] %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            tz_name=timezone,
        )
    )
    logger.addHandler(handler)
    return logger


def log_event(event: str, **fields: object) -> str:
    payload = {"event": event, **fields}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def redact_sensitive_text(value: object) -> str:
    text = str(value)
    patterns = (
        (r"(?i)(servicekey=)([^&\s]+)", r"\1***"),
        (r"(?i)(api[_-]?key=)([^&\s]+)", r"\1***"),
        (r"(?i)(service_api_key\s*[=:]\s*)([^\s,}]+)", r"\1***"),
    )
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text
