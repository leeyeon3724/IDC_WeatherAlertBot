from __future__ import annotations

import threading

import pytest
import requests

from app.services import notifier as notifier_module
from app.services.notifier import DoorayNotifier, DoorayResponseError, NotificationError


class DummyResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        json_body: object | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body or {
            "header": {
                "isSuccessful": True,
                "resultCode": "0",
                "resultMessage": "Success",
            }
        }
        self._json_error = json_error

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            error = requests.HTTPError(f"http error {self.status_code}")
            error.response = self
            raise error

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._json_body


class FakeSession:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.closed = False

    def post(self, *args, **kwargs):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


class CapturingSession:
    """POST 요청 payload를 캡처하는 세션."""

    def __init__(self) -> None:
        self.captured: list[dict] = []
        self.closed = False

    def post(self, url: str, **kwargs) -> DummyResponse:
        self.captured.append(kwargs.get("json", {}))
        return DummyResponse()

    def close(self) -> None:
        self.closed = True


def test_notifier_retries_then_succeeds_on_timeout() -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout"),
            DummyResponse(),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=2,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.send("hello")
    assert session.calls == 2


def test_notifier_retries_on_http_5xx_then_succeeds() -> None:
    session = FakeSession([DummyResponse(status_code=503), DummyResponse()])
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=2,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.send("hello")
    assert session.calls == 2


def test_notifier_does_not_retry_on_http_4xx() -> None:
    session = FakeSession([DummyResponse(status_code=400), DummyResponse()])
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    with pytest.raises(NotificationError) as exc_info:
        notifier.send("hello")
    assert exc_info.value.attempts == 1
    assert isinstance(exc_info.value.last_error, requests.HTTPError)
    assert session.calls == 1


def test_notifier_does_not_retry_on_unsuccessful_dooray_body() -> None:
    session = FakeSession(
        [
            DummyResponse(
                json_body={
                    "header": {
                        "isSuccessful": False,
                        "resultCode": "INVALID_PAYLOAD",
                        "resultMessage": "text field is required",
                    }
                }
            ),
            DummyResponse(),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    with pytest.raises(NotificationError) as exc_info:
        notifier.send("hello")
    assert exc_info.value.attempts == 1
    assert isinstance(exc_info.value.last_error, DoorayResponseError)
    assert "INVALID_PAYLOAD" in str(exc_info.value.last_error)
    assert "text field is required" in str(exc_info.value.last_error)
    assert session.calls == 1


def test_notifier_does_not_retry_when_response_json_parse_fails() -> None:
    session = FakeSession(
        [
            DummyResponse(json_error=ValueError("invalid json")),
            DummyResponse(),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    with pytest.raises(NotificationError) as exc_info:
        notifier.send("hello")
    assert exc_info.value.attempts == 1
    assert isinstance(exc_info.value.last_error, DoorayResponseError)
    assert session.calls == 1


def test_notifier_raises_after_max_retries() -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout-1"),
            requests.Timeout("timeout-2"),
            requests.Timeout("timeout-3"),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    with pytest.raises(NotificationError) as exc_info:
        notifier.send("hello")
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, requests.RequestException)
    assert session.calls == 3


def test_notifier_circuit_breaker_blocks_until_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout-1"),
            requests.Timeout("timeout-2"),
            DummyResponse(),
        ]
    )
    current = [0.0]
    monkeypatch.setattr(notifier_module.time, "monotonic", lambda: current[0])

    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        circuit_breaker_enabled=True,
        circuit_failure_threshold=2,
        circuit_reset_sec=30,
        session=session,
    )

    with pytest.raises(NotificationError) as first:
        notifier.send("hello")
    assert first.value.attempts == 1

    with pytest.raises(NotificationError) as second:
        notifier.send("hello")
    assert second.value.attempts == 1
    assert session.calls == 2

    with pytest.raises(NotificationError) as blocked:
        notifier.send("hello")
    assert blocked.value.attempts == 0
    assert session.calls == 2

    current[0] = 31.0
    notifier.send("hello")
    assert session.calls == 3


def test_notifier_backoff_stays_zero_when_retry_delay_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """retry_delay_sec=0 설정 시 모든 재시도에서 sleep이 호출되지 않아야 한다."""
    slept: list[float] = []
    monkeypatch.setattr(notifier_module.time, "sleep", lambda s: slept.append(s))

    session = FakeSession(
        [
            requests.Timeout("timeout-1"),
            requests.Timeout("timeout-2"),
            DummyResponse(),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.send("hello")
    assert session.calls == 3
    assert slept == [], "retry_delay_sec=0 설정 시 sleep이 호출되어서는 안 됨"


def test_notifier_backoff_doubles_when_retry_delay_is_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(notifier_module.time, "sleep", lambda s: slept.append(s))

    session = FakeSession(
        [
            requests.Timeout("timeout-1"),
            requests.Timeout("timeout-2"),
            DummyResponse(),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=1,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.send("hello")
    assert session.calls == 3
    assert slept == [1, 2]


def test_notifier_circuit_disabled_never_blocks_send() -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout-1"),
            requests.Timeout("timeout-2"),
            requests.Timeout("timeout-3"),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        circuit_breaker_enabled=False,
        circuit_failure_threshold=1,
        circuit_reset_sec=30,
        session=session,
    )

    with pytest.raises(NotificationError) as first:
        notifier.send("hello")
    with pytest.raises(NotificationError) as second:
        notifier.send("hello")

    assert first.value.attempts == 1
    assert second.value.attempts == 1
    assert session.calls == 2
    assert notifier._consecutive_failures == 0
    assert notifier._circuit_open_until_monotonic is None


def test_notifier_payload_includes_bot_name_and_message() -> None:
    """전송 payload에 botName과 text가 올바르게 포함되어야 한다."""
    session = CapturingSession()
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="날씨봇",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.send("강풍 특보 발효")

    assert len(session.captured) == 1
    payload = session.captured[0]
    assert payload["botName"] == "날씨봇"
    assert payload["text"] == "강풍 특보 발효"
    assert "attachments" not in payload


def test_notifier_payload_includes_attachment_when_report_url_given() -> None:
    """report_url 제공 시 attachments가 올바른 구조로 포함되어야 한다."""
    session = CapturingSession()
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="날씨봇",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.send("강풍 특보 발효", report_url="https://example.com/report/1")

    assert len(session.captured) == 1
    payload = session.captured[0]
    assert payload["botName"] == "날씨봇"
    assert payload["text"] == "강풍 특보 발효"
    attachments = payload["attachments"]
    assert isinstance(attachments, list) and len(attachments) == 1
    assert attachments[0]["titleLink"] == "https://example.com/report/1"
    assert attachments[0]["color"] == "blue"


def test_notifier_close_closes_underlying_session() -> None:
    session = FakeSession([DummyResponse()])
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        session=session,
    )

    notifier.close()
    assert session.closed is True


def test_notifier_circuit_breaker_consecutive_failures_thread_safe() -> None:
    """다중 스레드에서 동시에 send()가 실패해도 _consecutive_failures가 정확히 집계되어야 한다."""
    thread_count = 8
    barrier = threading.Barrier(thread_count)

    class BarrierSession:
        def post(self, *args, **kwargs) -> None:
            barrier.wait()
            raise requests.Timeout("concurrent timeout")

    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=0,
        circuit_breaker_enabled=True,
        circuit_failure_threshold=thread_count + 1,
        circuit_reset_sec=300,
        session=BarrierSession(),
    )

    errors: list[NotificationError] = []

    def worker() -> None:
        try:
            notifier.send("hello")
        except NotificationError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == thread_count
    assert notifier._consecutive_failures == thread_count


def test_notifier_send_rate_limit_applies_globally(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([DummyResponse(), DummyResponse()])
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=1,
        retry_delay_sec=0,
        send_rate_limit_per_sec=1.0,
        session=session,
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(notifier_module.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(notifier_module.time, "sleep", lambda sec: sleep_calls.append(sec))

    notifier.send("hello-1")
    notifier.send("hello-2")

    assert session.calls == 2
    assert sleep_calls == [1.0]
