from __future__ import annotations

import logging

import requests


class NotificationError(RuntimeError):
    """Raised when message delivery fails."""


class DoorayNotifier:
    def __init__(
        self,
        hook_url: str,
        bot_name: str,
        timeout_sec: int = 5,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.hook_url = hook_url
        self.bot_name = bot_name
        self.timeout_sec = timeout_sec
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

        try:
            response = self.session.post(
                self.hook_url,
                json=payload,
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NotificationError(f"Dooray webhook send failed: {exc}") from exc

        self.logger.debug("notifier.sent report_url=%s", bool(report_url))

