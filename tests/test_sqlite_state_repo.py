from __future__ import annotations

from datetime import UTC, datetime

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
