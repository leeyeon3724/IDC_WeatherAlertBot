from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.models import AlertNotification
from app.repositories.state_models import StoredNotification, parse_iso_to_utc, utc_now_iso

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
        now = utc_now_iso()
        new_count = 0
        with self._connect() as conn:
            for notification in notifications:
                existing = conn.execute(
                    """
                    SELECT area_code, message, report_url
                    FROM notifications
                    WHERE event_id = ?
                    """,
                    (notification.event_id,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO notifications (
                          event_id, area_code, message, report_url, sent,
                          first_seen_at, updated_at, last_sent_at
                        ) VALUES (?, ?, ?, ?, 0, ?, ?, NULL)
                        """,
                        (
                            notification.event_id,
                            notification.area_code,
                            notification.message,
                            notification.report_url,
                            now,
                            now,
                        ),
                    )
                    new_count += 1
                    continue

                if (
                    existing["area_code"] != notification.area_code
                    or existing["message"] != notification.message
                    or existing["report_url"] != notification.report_url
                ):
                    conn.execute(
                        """
                        UPDATE notifications
                        SET area_code = ?, message = ?, report_url = ?, updated_at = ?
                        WHERE event_id = ?
                        """,
                        (
                            notification.area_code,
                            notification.message,
                            notification.report_url,
                            now,
                            notification.event_id,
                        ),
                    )
        return new_count

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
        if self.mark_many_sent([event_id]) > 0:
            return True

        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM notifications WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return exists is not None

    def mark_many_sent(self, event_ids: Iterable[str]) -> int:
        ids = [event_id for event_id in event_ids if event_id]
        if not ids:
            return 0

        placeholders = ",".join("?" for _ in ids)
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE notifications
                SET sent = 1,
                    updated_at = ?,
                    last_sent_at = ?
                WHERE sent = 0
                  AND event_id IN ({placeholders})
                """,
                (now, now, *ids),
            )
            return int(cursor.rowcount)

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

        if include_unsent:
            select_query = """
                SELECT event_id, updated_at, last_sent_at, first_seen_at
                FROM notifications
            """
            params: tuple[object, ...] = ()
        else:
            select_query = """
                SELECT event_id, updated_at, last_sent_at, first_seen_at
                FROM notifications
                WHERE sent = 1
            """
            params = ()

        removable: list[str] = []
        with self._connect() as conn:
            rows = conn.execute(select_query, params).fetchall()
            for row in rows:
                reference_time = (
                    parse_iso_to_utc(row["updated_at"])
                    or parse_iso_to_utc(row["last_sent_at"])
                    or parse_iso_to_utc(row["first_seen_at"])
                )
                if reference_time is None:
                    continue
                if reference_time <= threshold:
                    removable.append(str(row["event_id"]))

            if removable and not dry_run:
                placeholders = ",".join("?" for _ in removable)
                conn.execute(
                    f"DELETE FROM notifications WHERE event_id IN ({placeholders})",
                    tuple(removable),
                )

        return len(removable)

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
