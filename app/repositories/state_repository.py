from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from app.domain.models import AlertNotification
from app.repositories.state_models import StoredNotification


class StateRepository(Protocol):
    def upsert_notifications(self, notifications: Iterable[AlertNotification]) -> int:
        ...

    def get_unsent(self, area_code: str | None = None) -> list[StoredNotification]:
        ...

    def mark_sent(self, event_id: str) -> bool:
        ...

    def mark_many_sent(self, event_ids: Iterable[str]) -> int:
        ...

    def cleanup_stale(
        self,
        *,
        days: int = 30,
        include_unsent: bool = False,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> int:
        ...

    @property
    def total_count(self) -> int:
        ...

    @property
    def pending_count(self) -> int:
        ...
