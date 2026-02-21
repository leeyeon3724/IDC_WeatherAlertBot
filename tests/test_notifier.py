from __future__ import annotations

import pytest
import requests

from app.services import notifier as notifier_module
from app.services.notifier import DoorayNotifier, NotificationError


class DummyResponse:
    def __init__(self, should_raise: bool = False):
        self.should_raise = should_raise

    def raise_for_status(self) -> None:
        if self.should_raise:
            raise requests.HTTPError("http error")


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def post(self, *args, **kwargs):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_notifier_retries_then_succeeds() -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout"),
            DummyResponse(should_raise=False),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=2,
        retry_delay_sec=0,
        session=session,
    )

    notifier.send("hello")
    assert session.calls == 2


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
        session=session,
    )

    try:
        notifier.send("hello")
        assert False, "NotificationError expected"
    except NotificationError as exc:
        assert exc.attempts == 3
        assert isinstance(exc.last_error, requests.RequestException)
        assert session.calls == 3


def test_notifier_circuit_breaker_blocks_until_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            requests.Timeout("timeout-1"),
            requests.Timeout("timeout-2"),
            DummyResponse(should_raise=False),
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
            DummyResponse(should_raise=False),
        ]
    )
    notifier = DoorayNotifier(
        hook_url="https://hook.example",
        bot_name="test-bot",
        timeout_sec=1,
        max_retries=3,
        retry_delay_sec=0,
        session=session,
    )

    notifier.send("hello")
    assert session.calls == 3
    assert slept == [], "retry_delay_sec=0 설정 시 sleep이 호출되어서는 안 됨"
