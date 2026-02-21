from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha1
from pathlib import Path
from typing import Any

from app.domain.models import AlertNotification
from app.logging_utils import log_event
from app.observability import events
from app.repositories.state_models import StoredNotification, parse_iso_to_utc, utc_now_iso

STATE_SCHEMA_VERSION = 2


class JsonStateRepository:
    def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
        self.file_path = Path(file_path)
        self.logger = logger or logging.getLogger("weather_alert_bot.state")
        self._state: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._state = {}
            return

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except json.JSONDecodeError as exc:
            backup_path = self._backup_corrupted_file()
            self.logger.error(
                log_event(
                    events.STATE_INVALID_JSON,
                    file=str(self.file_path),
                    backup=str(backup_path) if backup_path is not None else None,
                    error=str(exc),
                )
            )
            self._state = {}
            self._persist()
            return
        except OSError as exc:
            self.logger.error(
                log_event(
                    events.STATE_READ_FAILED,
                    file=str(self.file_path),
                    error=str(exc),
                )
            )
            self._state = {}
            return

        self._state, migrated = self._normalize_state(raw)
        if migrated:
            self._persist()

    def _backup_corrupted_file(self) -> Path | None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = self.file_path.with_name(f"{self.file_path.name}.broken-{timestamp}")
        try:
            self.file_path.replace(backup_path)
            return backup_path
        except OSError as exc:
            self.logger.error(
                log_event(
                    events.STATE_BACKUP_FAILED,
                    file=str(self.file_path),
                    error=str(exc),
                )
            )
            return None

    def _normalize_state(self, raw: Any) -> tuple[dict[str, dict[str, Any]], bool]:
        if not isinstance(raw, dict):
            return {}, True

        migrated = False
        now = utc_now_iso()
        normalized: dict[str, dict[str, Any]] = {}

        if "events" in raw:
            events_raw = raw.get("events")
            if not isinstance(events_raw, dict):
                return {}, True
            if raw.get("version") != STATE_SCHEMA_VERSION:
                migrated = True
            raw = events_raw

        is_legacy = True
        for value in raw.values():
            if not isinstance(value, (int, bool)):
                is_legacy = False
                break

        if is_legacy:
            migrated = True
            for message, status in raw.items():
                message_text = str(message)
                event_id = f"legacy:{sha1(message_text.encode('utf-8')).hexdigest()[:20]}"
                sent = bool(status)
                normalized[event_id] = {
                    "area_code": "UNKNOWN",
                    "message": message_text,
                    "report_url": None,
                    "sent": sent,
                    "first_seen_at": now,
                    "updated_at": now,
                    "last_sent_at": now if sent else None,
                }
            return normalized, migrated

        for event_id, record in raw.items():
            if not isinstance(record, dict):
                migrated = True
                continue

            normalized_event_id = str(event_id)
            normalized_record = {
                "area_code": str(record.get("area_code", "UNKNOWN")),
                "message": str(record.get("message", "")),
                "report_url": record.get("report_url"),
                "sent": bool(record.get("sent", False)),
                "first_seen_at": str(record.get("first_seen_at", now)),
                "updated_at": str(record.get("updated_at", now)),
                "last_sent_at": record.get("last_sent_at"),
            }
            normalized[normalized_event_id] = normalized_record
        return normalized, migrated

    def _persist(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        payload = {
            "version": STATE_SCHEMA_VERSION,
            "events": self._state,
        }
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            temp_path.replace(self.file_path)
        except OSError as exc:
            self.logger.error(
                log_event(
                    events.STATE_PERSIST_FAILED,
                    file=str(self.file_path),
                    temp_file=str(temp_path),
                    error=str(exc),
                )
            )
            raise

    def upsert_notifications(self, notifications: Iterable[AlertNotification]) -> int:
        now = utc_now_iso()
        changed = False
        new_count = 0

        for notification in notifications:
            existing = self._state.get(notification.event_id)
            if existing is None:
                self._state[notification.event_id] = {
                    "area_code": notification.area_code,
                    "message": notification.message,
                    "report_url": notification.report_url,
                    "sent": False,
                    "first_seen_at": now,
                    "updated_at": now,
                    "last_sent_at": None,
                }
                changed = True
                new_count += 1
                continue

            record_changed = False
            if existing.get("area_code") != notification.area_code:
                existing["area_code"] = notification.area_code
                record_changed = True
            if existing.get("message") != notification.message:
                existing["message"] = notification.message
                record_changed = True
            if existing.get("report_url") != notification.report_url:
                existing["report_url"] = notification.report_url
                record_changed = True
            if record_changed:
                existing["updated_at"] = now
                changed = True

        if changed:
            self._persist()
        return new_count

    def get_unsent(self, area_code: str | None = None) -> list[StoredNotification]:
        rows: list[StoredNotification] = []
        for event_id, record in self._state.items():
            if bool(record.get("sent", False)):
                continue
            if area_code and record.get("area_code") != area_code:
                continue
            rows.append(
                StoredNotification(
                    event_id=event_id,
                    area_code=str(record.get("area_code", "UNKNOWN")),
                    message=str(record.get("message", "")),
                    report_url=record.get("report_url"),
                    sent=False,
                    first_seen_at=str(record.get("first_seen_at", "")),
                    updated_at=str(record.get("updated_at", "")),
                    last_sent_at=record.get("last_sent_at"),
                )
            )
        return sorted(rows, key=lambda row: row.first_seen_at)

    def all_notifications(self) -> list[StoredNotification]:
        rows: list[StoredNotification] = []
        for event_id, record in self._state.items():
            rows.append(
                StoredNotification(
                    event_id=event_id,
                    area_code=str(record.get("area_code", "UNKNOWN")),
                    message=str(record.get("message", "")),
                    report_url=record.get("report_url"),
                    sent=bool(record.get("sent", False)),
                    first_seen_at=str(record.get("first_seen_at", "")),
                    updated_at=str(record.get("updated_at", "")),
                    last_sent_at=record.get("last_sent_at"),
                )
            )
        return sorted(rows, key=lambda row: row.first_seen_at)

    def mark_sent(self, event_id: str) -> bool:
        record = self._state.get(event_id)
        if not record:
            return False
        if bool(record.get("sent", False)):
            return True
        return self.mark_many_sent([event_id]) > 0

    def mark_many_sent(self, event_ids: Iterable[str]) -> int:
        now = utc_now_iso()
        changed = False
        marked_count = 0

        for event_id in event_ids:
            record = self._state.get(event_id)
            if not record:
                continue
            if bool(record.get("sent", False)):
                continue
            record["sent"] = True
            record["updated_at"] = now
            record["last_sent_at"] = now
            changed = True
            marked_count += 1

        if changed:
            self._persist()
        return marked_count

    def cleanup_stale(
        self,
        *,
        days: int = 30,
        include_unsent: bool = False,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> int:
        if days < 0:
            raise ValueError("days must be >= 0")

        current = now or datetime.now(UTC)
        threshold = current - timedelta(days=days)
        removable: list[str] = []

        for event_id, record in self._state.items():
            is_sent = bool(record.get("sent", False))
            if not include_unsent and not is_sent:
                continue

            reference_time = (
                parse_iso_to_utc(record.get("updated_at"))
                or parse_iso_to_utc(record.get("last_sent_at"))
                or parse_iso_to_utc(record.get("first_seen_at"))
            )
            if reference_time is None:
                continue
            if reference_time <= threshold:
                removable.append(event_id)

        if removable and not dry_run:
            for event_id in removable:
                self._state.pop(event_id, None)
            self._persist()

        return len(removable)

    @property
    def total_count(self) -> int:
        return len(self._state)

    @property
    def pending_count(self) -> int:
        return sum(1 for record in self._state.values() if not bool(record.get("sent", False)))
