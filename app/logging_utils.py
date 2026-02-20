from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo


class TimezoneFormatter(logging.Formatter):
    def __init__(self, *args, tz_name: str = "Asia/Seoul", **kwargs) -> None:
        super().__init__(*args, **kwargs)
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

