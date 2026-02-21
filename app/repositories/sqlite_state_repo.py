from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.models import AlertNotification
from app.repositories.state_models import StoredNotification, utc_now_iso

SQLITE_BUSY_TIMEOUT_MS = 30_000
SQLITE_JOURNAL_MODE = "WAL"


class SqliteStateRepository:
    def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
        self.file_path = Path(file_path)
        self.logger = logger or logging.getLogger("weather_alert_bot.state.sqlite")
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.file_path)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                  event_id TEXT PRIMARY KEY,
                  area_code TEXT NOT NULL,
                  message TEXT NOT NULL,
                  report_url TEXT,
                  sent INTEGER NOT NULL DEFAULT 0,
                  first_seen_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  last_sent_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notifications_sent_area
                  ON notifications(sent, area_code, first_seen_at)
                """
            )

    def upsert_notifications(self, notifications: Iterable[AlertNotification]) -> int:
        by_event_id = {notification.event_id: notification for notification in notifications}
        if not by_event_id:
            return 0

        event_ids = list(by_event_id.keys())
        now = utc_now_iso()
        rows = [
            (
                event_id,
                notification.area_code,
                notification.message,
                notification.report_url,
                now,
                now,
            )
            for event_id, notification in by_event_id.items()
        ]
        with self._connect() as conn:
            existing = self._fetch_existing(conn, event_ids=event_ids)
            conn.executemany(
                """
                INSERT INTO notifications (
                  event_id, area_code, message, report_url, sent,
                  first_seen_at, updated_at, last_sent_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, NULL)
                ON CONFLICT(event_id) DO UPDATE SET
                  area_code  = excluded.area_code,
                  message    = excluded.message,
                  report_url = excluded.report_url,
                  updated_at = excluded.updated_at
                WHERE
                  notifications.area_code  IS NOT excluded.area_code
                  OR notifications.message    IS NOT excluded.message
                  OR notifications.report_url IS NOT excluded.report_url
                """,
                rows,
            )
        return sum(1 for event_id in event_ids if event_id not in existing)

    def upsert_stored_notifications(self, notifications: Iterable[StoredNotification]) -> int:
        by_event_id = {notification.event_id: notification for notification in notifications}
        if not by_event_id:
            return 0

        event_ids = list(by_event_id.keys())
        now = utc_now_iso()
        with self._connect() as conn:
            existing = self._fetch_existing(conn, event_ids=event_ids)
            rows: list[tuple[object, ...]] = []
            for event_id, notification in by_event_id.items():
                first_seen_at = notification.first_seen_at or now
                updated_at = notification.updated_at or first_seen_at
                last_sent_at = notification.last_sent_at
                rows.append(
                    (
                        event_id,
                        notification.area_code,
                        notification.message,
                        notification.report_url,
                        1 if notification.sent else 0,
                        first_seen_at,
                        updated_at,
                        last_sent_at,
                    )
                )

            conn.executemany(
                """
                INSERT INTO notifications (
                  event_id, area_code, message, report_url, sent,
                  first_seen_at, updated_at, last_sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                  area_code = excluded.area_code,
                  message = excluded.message,
                  report_url = excluded.report_url,
                  sent = excluded.sent,
                  first_seen_at = excluded.first_seen_at,
                  updated_at = excluded.updated_at,
                  last_sent_at = excluded.last_sent_at
                """,
                rows,
            )
        return sum(1 for event_id in event_ids if event_id not in existing)

    def get_unsent(self, area_code: str | None = None) -> list[StoredNotification]:
        where_clause = "WHERE sent = 0"
        params: tuple[object, ...] = ()
        if area_code:
            where_clause += " AND area_code = ?"
            params = (area_code,)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT event_id, area_code, message, report_url, sent,
                       first_seen_at, updated_at, last_sent_at
                FROM notifications
                {where_clause}
                ORDER BY first_seen_at ASC
                """,
                params,
            ).fetchall()

        return [
            StoredNotification(
                event_id=str(row["event_id"]),
                area_code=str(row["area_code"]),
                message=str(row["message"]),
                report_url=row["report_url"],
                sent=bool(row["sent"]),
                first_seen_at=str(row["first_seen_at"]),
                updated_at=str(row["updated_at"]),
                last_sent_at=row["last_sent_at"],
            )
            for row in rows
        ]

    def mark_sent(self, event_id: str) -> bool:
        if not event_id:
            return False
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE notifications
                SET sent = 1, updated_at = ?, last_sent_at = ?
                WHERE sent = 0 AND event_id = ?
                """,
                (now, now, event_id),
            )
            row = conn.execute(
                "SELECT 1 FROM notifications WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row is not None

    def mark_many_sent(self, event_ids: Iterable[str]) -> int:
        ids = list(dict.fromkeys(event_id for event_id in event_ids if event_id))
        if not ids:
            return 0

        now = utc_now_iso()
        with self._connect() as conn:
            before_changes = conn.total_changes
            conn.executemany(
                """
                UPDATE notifications
                SET sent = 1,
                    updated_at = ?,
                    last_sent_at = ?
                WHERE sent = 0
                  AND event_id = ?
                """,
                ((now, now, event_id) for event_id in ids),
            )
            return conn.total_changes - before_changes

    @staticmethod
    def _fetch_existing(
        conn: sqlite3.Connection,
        *,
        event_ids: list[str],
        chunk_size: int = 500,
    ) -> dict[str, sqlite3.Row]:
        existing: dict[str, sqlite3.Row] = {}
        for start in range(0, len(event_ids), chunk_size):
            chunk = event_ids[start : start + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT event_id, area_code, message, report_url
                FROM notifications
                WHERE event_id IN ({placeholders})
                """,
                tuple(chunk),
            ).fetchall()
            for row in rows:
                existing[str(row["event_id"])] = row
        return existing

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
        threshold_iso = threshold.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sent_filter = "" if include_unsent else "sent = 1 AND "
        where_clause = f"WHERE {sent_filter}COALESCE(updated_at, last_sent_at, first_seen_at) <= ?"

        with self._connect() as conn:
            if dry_run:
                row = conn.execute(
                    f"SELECT COUNT(*) AS count FROM notifications {where_clause}",
                    (threshold_iso,),
                ).fetchone()
                return int(row["count"]) if row is not None else 0

            cursor = conn.execute(
                f"DELETE FROM notifications {where_clause}",
                (threshold_iso,),
            )
            return int(cursor.rowcount)

    @property
    def total_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM notifications").fetchone()
        return int(row["count"]) if row is not None else 0

    @property
    def pending_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE sent = 0"
            ).fetchone()
        return int(row["count"]) if row is not None else 0
