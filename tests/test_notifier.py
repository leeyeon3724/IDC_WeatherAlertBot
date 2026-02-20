from __future__ import annotations

import requests

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

