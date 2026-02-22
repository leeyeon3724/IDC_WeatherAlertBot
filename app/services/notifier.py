from __future__ import annotations

import logging
import threading
import time

import requests

from app.logging_utils import log_event, redact_sensitive_text
from app.observability import events


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


class DoorayResponseError(RuntimeError):
    """Raised when Dooray response body indicates a failed delivery."""

    def __init__(
        self,
        message: str,
        *,
        result_code: object | None = None,
        result_message: object | None = None,
    ) -> None:
        super().__init__(message)
        self.result_code = result_code
        self.result_message = result_message


class DoorayNotifier:
    def __init__(
        self,
        hook_url: str,
        bot_name: str,
        timeout_sec: int = 5,
        connect_timeout_sec: int | None = None,
        read_timeout_sec: int | None = None,
        max_retries: int = 3,
        retry_delay_sec: int = 1,
        circuit_breaker_enabled: bool = True,
        circuit_failure_threshold: int = 5,
        circuit_reset_sec: int = 300,
        send_rate_limit_per_sec: float = 1.0,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.hook_url = hook_url
        self.bot_name = bot_name
        self.timeout_sec = timeout_sec
        self.connect_timeout_sec = connect_timeout_sec or timeout_sec
        self.read_timeout_sec = read_timeout_sec or timeout_sec
        self.max_retries = max(1, max_retries)
        self.retry_delay_sec = max(0, retry_delay_sec)
        self.circuit_breaker_enabled = circuit_breaker_enabled
        self.circuit_failure_threshold = max(1, circuit_failure_threshold)
        self.circuit_reset_sec = max(1, circuit_reset_sec)
        self.send_rate_limit_per_sec = max(0.0, send_rate_limit_per_sec)
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger("weather_alert_bot.notifier")
        self._consecutive_failures = 0
        self._circuit_open_until_monotonic: float | None = None
        self._next_send_allowed_monotonic = 0.0
        self._lock = threading.Lock()

    def close(self) -> None:
        self.session.close()

    def _is_circuit_open(self, now: float) -> bool:
        return (
            self.circuit_breaker_enabled
            and self._circuit_open_until_monotonic is not None
            and now < self._circuit_open_until_monotonic
        )

    def _close_circuit_if_ready(self, now: float) -> None:
        if not self.circuit_breaker_enabled:
            return
        if self._circuit_open_until_monotonic is None:
            return
        if now < self._circuit_open_until_monotonic:
            return
        self._circuit_open_until_monotonic = None
        self._consecutive_failures = 0
        self.logger.info(log_event(events.NOTIFICATION_CIRCUIT_CLOSED))

    def _acquire_send_slot(self) -> None:
        if self.send_rate_limit_per_sec <= 0:
            return

        min_interval_sec = 1.0 / self.send_rate_limit_per_sec
        with self._lock:
            now = time.monotonic()
            slot_time = max(now, self._next_send_allowed_monotonic)
            self._next_send_allowed_monotonic = slot_time + min_interval_sec
            wait_sec = slot_time - now

        if wait_sec > 0:
            time.sleep(wait_sec)

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, DoorayResponseError):
            return False
        if isinstance(exc, requests.Timeout):
            return True
        if isinstance(exc, requests.ConnectionError):
            return True
        if isinstance(exc, requests.HTTPError):
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is None:
                return False
            return 500 <= status_code < 600
        if isinstance(exc, requests.RequestException):
            return True
        return False

    @staticmethod
    def _validate_response_body(response: requests.Response) -> None:
        try:
            response_body = response.json()
        except ValueError:
            # Dooray webhook may return an empty/non-JSON body even when delivery
            # succeeded with HTTP 200. Treat parse failure as success.
            return

        header = response_body.get("header") if isinstance(response_body, dict) else None
        if not isinstance(header, dict):
            raise DoorayResponseError("Dooray response missing 'header' block")

        is_successful = header.get("isSuccessful")
        if is_successful is True:
            return

        result_code = header.get("resultCode")
        result_message = header.get("resultMessage")
        raise DoorayResponseError(
            "Dooray response unsuccessful: "
            f"resultCode={result_code!r}, resultMessage={result_message!r}",
            result_code=result_code,
            result_message=result_message,
        )

    def send(self, message: str, report_url: str | None = None) -> None:
        with self._lock:
            now = time.monotonic()
            self._close_circuit_if_ready(now)
            if self._is_circuit_open(now):
                assert self._circuit_open_until_monotonic is not None
                remaining_sec = int(self._circuit_open_until_monotonic - now)
                self.logger.warning(
                    log_event(
                        events.NOTIFICATION_CIRCUIT_BLOCKED,
                        remaining_sec=remaining_sec,
                        consecutive_failures=self._consecutive_failures,
                    )
                )
                raise NotificationError(
                    "Dooray webhook send blocked by circuit breaker",
                    attempts=0,
                    last_error=RuntimeError("circuit_open"),
                )

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
        attempts = 0
        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                self._acquire_send_slot()
                response = self.session.post(
                    self.hook_url,
                    json=payload,
                    timeout=(self.connect_timeout_sec, self.read_timeout_sec),
                )
                response.raise_for_status()
                self._validate_response_body(response)
                with self._lock:
                    self._consecutive_failures = 0
                self.logger.debug("notifier.sent report_url=%s", bool(report_url))
                return
            except (requests.RequestException, DoorayResponseError) as exc:
                last_error = exc
                if attempt == self.max_retries or not self._is_retryable_error(exc):
                    break
                self.logger.warning(
                    log_event(
                        events.NOTIFICATION_RETRY,
                        attempt=attempt,
                        max_retries=self.max_retries,
                        error=redact_sensitive_text(exc),
                        backoff_sec=backoff_seconds,
                    )
                )
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
                backoff_seconds = max(backoff_seconds * 2, self.retry_delay_sec)

        with self._lock:
            if self.circuit_breaker_enabled:
                self._consecutive_failures += 1
                if (
                    self._consecutive_failures >= self.circuit_failure_threshold
                    and self._circuit_open_until_monotonic is None
                ):
                    self._circuit_open_until_monotonic = time.monotonic() + self.circuit_reset_sec
                    self.logger.warning(
                        log_event(
                            events.NOTIFICATION_CIRCUIT_OPENED,
                            consecutive_failures=self._consecutive_failures,
                            reset_sec=self.circuit_reset_sec,
                        )
                    )

        raise NotificationError(
            (
                f"Dooray webhook send failed: {last_error}"
                if last_error is not None
                else "Dooray webhook send failed"
            ),
            attempts=attempts,
            last_error=last_error,
        )
