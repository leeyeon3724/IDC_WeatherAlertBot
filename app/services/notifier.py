from __future__ import annotations

import logging
import time

import requests


class NotificationError(RuntimeError):
    """Raised when message delivery fails."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int = 1,
        last_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class DoorayNotifier:
    def __init__(
        self,
        hook_url: str,
        bot_name: str,
        timeout_sec: int = 5,
        max_retries: int = 3,
        retry_delay_sec: int = 1,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.hook_url = hook_url
        self.bot_name = bot_name
        self.timeout_sec = timeout_sec
        self.max_retries = max(1, max_retries)
        self.retry_delay_sec = max(0, retry_delay_sec)
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger("weather_alert_bot.notifier")

    def send(self, message: str, report_url: str | None = None) -> None:
        payload: dict[str, object] = {
            "botName": self.bot_name,
            "text": message,
        }
        if report_url:
            payload["attachments"] = [
                {
                    "title": "> 해당 특보 통보문 바로가기",
                    "titleLink": report_url,
                    "color": "blue",
                }
            ]

        backoff_seconds = self.retry_delay_sec
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    self.hook_url,
                    json=payload,
                    timeout=self.timeout_sec,
                )
                response.raise_for_status()
                self.logger.debug("notifier.sent report_url=%s", bool(report_url))
                return
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                self.logger.warning(
                    "notifier.retry attempt=%s reason=%s backoff=%ss",
                    attempt,
                    exc,
                    backoff_seconds,
                )
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
                backoff_seconds = max(backoff_seconds * 2, 1)

        raise NotificationError(
            "Dooray webhook send failed",
            attempts=self.max_retries,
            last_error=last_error,
        )
