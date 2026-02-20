from __future__ import annotations

from pathlib import Path

from app.domain.models import AlertNotification
from app.repositories.json_state_repo import JsonStateRepository
from app.repositories.sqlite_state_repo import SqliteStateRepository
from app.repositories.state_migration import migrate_json_to_sqlite


def _seed_json_state(json_file: Path) -> None:
    source_repo = JsonStateRepository(json_file)
    source_repo.upsert_notifications(
        [
            AlertNotification(
                event_id="event:sent",
                area_code="11B00000",
                message="sent message",
                report_url="https://example.com/sent",
            ),
            AlertNotification(
                event_id="event:unsent",
                area_code="11C00000",
                message="unsent message",
                report_url=None,
            ),
        ]
    )
    source_repo.mark_sent("event:sent")


def test_migrate_json_to_sqlite_copies_records_and_sent_status(tmp_path) -> None:
    json_file = tmp_path / "state.json"
    sqlite_file = tmp_path / "state.db"
    _seed_json_state(json_file)

    result = migrate_json_to_sqlite(
        json_state_file=json_file,
        sqlite_state_file=sqlite_file,
    )

    sqlite_repo = SqliteStateRepository(sqlite_file)
    unsent = sqlite_repo.get_unsent()

    assert result.total_records == 2
    assert result.inserted_records == 2
    assert result.sent_records == 1
    assert result.marked_sent_records == 1
    assert sqlite_repo.total_count == 2
    assert sqlite_repo.pending_count == 1
    assert len(unsent) == 1
    assert unsent[0].event_id == "event:unsent"


def test_migrate_json_to_sqlite_is_idempotent_for_existing_rows(tmp_path) -> None:
    json_file = tmp_path / "state.json"
    sqlite_file = tmp_path / "state.db"
    _seed_json_state(json_file)

    first = migrate_json_to_sqlite(
        json_state_file=json_file,
        sqlite_state_file=sqlite_file,
    )
    second = migrate_json_to_sqlite(
        json_state_file=json_file,
        sqlite_state_file=sqlite_file,
    )

    sqlite_repo = SqliteStateRepository(sqlite_file)

    assert first.inserted_records == 2
    assert second.inserted_records == 0
    assert second.sent_records == 1
    assert sqlite_repo.total_count == 2
    assert sqlite_repo.pending_count == 1
