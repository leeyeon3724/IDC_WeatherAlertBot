from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.models import AlertNotification
from app.repositories.sqlite_state_repo import (
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_JOURNAL_MODE,
    SqliteStateRepository,
)


def _notification(event_id: str, message: str = "테스트 메시지") -> AlertNotification:
    return AlertNotification(
        event_id=event_id,
        area_code="11B00000",
        message=message,
        report_url="https://example.com/report",
    )


def test_sqlite_state_repo_upsert_and_mark_sent(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")

    assert repo.upsert_notifications([_notification("event:1")]) == 1
    assert repo.pending_count == 1

    unsent = repo.get_unsent("11B00000")
    assert len(unsent) == 1
    assert unsent[0].event_id == "event:1"

    assert repo.mark_sent("event:1") is True
    assert repo.pending_count == 0


def test_sqlite_state_repo_updates_existing_event(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")

    assert repo.upsert_notifications([_notification("event:1", "first")]) == 1
    assert repo.upsert_notifications([_notification("event:1", "second")]) == 0

    unsent = repo.get_unsent("11B00000")
    assert len(unsent) == 1
    assert unsent[0].message == "second"


def test_sqlite_state_repo_cleanup_sent_only(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")
    repo.upsert_notifications([_notification("event:sent"), _notification("event:unsent")])
    repo.mark_sent("event:sent")
    old_time = "2020-01-01T00:00:00Z"
    with repo._connect() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET updated_at = ?, last_sent_at = ?
            WHERE event_id = ?
            """,
            (old_time, old_time, "event:sent"),
        )

    removed = repo.cleanup_stale(
        days=0,
        include_unsent=False,
        now=datetime(2026, 2, 21, tzinfo=UTC),
    )

    assert removed == 1
    assert repo.total_count == 1


def test_sqlite_state_repo_cleanup_dry_run(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")
    repo.upsert_notifications([_notification("event:sent")])
    repo.mark_sent("event:sent")
    old_time = "2020-01-01T00:00:00Z"
    with repo._connect() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET updated_at = ?, last_sent_at = ?
            WHERE event_id = ?
            """,
            (old_time, old_time, "event:sent"),
        )

    removed = repo.cleanup_stale(
        days=0,
        include_unsent=True,
        dry_run=True,
        now=datetime(2026, 2, 21, tzinfo=UTC),
    )

    assert removed == 1
    assert repo.total_count == 1


def test_sqlite_state_repo_configures_busy_timeout_and_wal(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")

    with repo._connect() as conn:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert int(busy_timeout) == SQLITE_BUSY_TIMEOUT_MS
    assert str(journal_mode).lower() == SQLITE_JOURNAL_MODE.lower()


def test_sqlite_state_repo_mark_many_sent_handles_duplicates(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")
    repo.upsert_notifications([_notification("event:1"), _notification("event:2")])

    marked = repo.mark_many_sent(["event:1", "event:1", "event:2"])

    assert marked == 2
    assert repo.pending_count == 0


def test_sqlite_state_repo_cleanup_stale_bulk_records(tmp_path) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")
    notifications = [_notification(f"event:{idx}") for idx in range(200)]
    repo.upsert_notifications(notifications)

    sent_ids = [f"event:{idx}" for idx in range(150)]
    repo.mark_many_sent(sent_ids)

    old_sent_ids = [f"event:{idx}" for idx in range(120)]
    old_time = "2020-01-01T00:00:00Z"
    with repo._connect() as conn:
        conn.executemany(
            """
            UPDATE notifications
            SET updated_at = ?, last_sent_at = ?
            WHERE event_id = ?
            """,
            ((old_time, old_time, event_id) for event_id in old_sent_ids),
        )

    removed = repo.cleanup_stale(
        days=30,
        include_unsent=False,
        now=datetime(2026, 2, 21, tzinfo=UTC),
    )

    assert removed == 120
    assert repo.total_count == 80


class _TracingConnection:
    def __init__(self, conn, counters: dict[str, int]) -> None:
        self._conn = conn
        self._counters = counters

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._conn.__exit__(exc_type, exc, tb)

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        self._counters["executemany"] = self._counters.get("executemany", 0) + 1
        return self._conn.executemany(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._conn, item)


def test_sqlite_state_repo_bulk_paths_use_batch_execution(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SqliteStateRepository(tmp_path / "state.db")
    counters: dict[str, int] = {"executemany": 0}
    original_connect = repo._connect

    def _tracked_connect():
        return _TracingConnection(original_connect(), counters)

    monkeypatch.setattr(repo, "_connect", _tracked_connect)
    notifications = [_notification(f"event:{idx}") for idx in range(120)]

    inserted = repo.upsert_notifications(notifications)
    marked = repo.mark_many_sent([notification.event_id for notification in notifications])

    assert inserted == 120
    assert marked == 120
    # Baseline regression guard:
    # - upsert_notifications: 1 batched insert
    # - mark_many_sent: 1 batched update
    assert counters["executemany"] == 2
