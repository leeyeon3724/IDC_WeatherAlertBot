from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.repositories.json_state_repo import JsonStateRepository
from app.repositories.sqlite_state_repo import SqliteStateRepository


@dataclass(frozen=True)
class JsonToSqliteMigrationResult:
    total_records: int
    inserted_records: int
    sent_records: int
    marked_sent_records: int


def migrate_json_to_sqlite(
    *,
    json_state_file: Path,
    sqlite_state_file: Path,
    logger: logging.Logger | None = None,
) -> JsonToSqliteMigrationResult:
    migration_logger = logger or logging.getLogger("weather_alert_bot.state_migration")
    source_repo = JsonStateRepository(
        Path(json_state_file),
        logger=migration_logger.getChild("json_source"),
    )
    target_repo = SqliteStateRepository(
        Path(sqlite_state_file),
        logger=migration_logger.getChild("sqlite_target"),
    )

    source_records = source_repo.all_notifications()
    inserted_records = target_repo.upsert_stored_notifications(source_records)
    sent_event_ids = [record.event_id for record in source_records if record.sent]
    marked_sent_records = len(sent_event_ids)

    return JsonToSqliteMigrationResult(
        total_records=len(source_records),
        inserted_records=inserted_records,
        sent_records=len(sent_event_ids),
        marked_sent_records=marked_sent_records,
    )
