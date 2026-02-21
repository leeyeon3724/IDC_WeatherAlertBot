from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.domain.health import ApiHealthState
from app.logging_utils import log_event
from app.observability import events

HEALTH_STATE_SCHEMA_VERSION = 1


class JsonHealthStateRepository:
    def __init__(self, file_path: Path, logger: logging.Logger | None = None) -> None:
        self.file_path = Path(file_path)
        self.logger = logger or logging.getLogger("weather_alert_bot.health_state")
        self._state = ApiHealthState()
        self._load()

    @property
    def state(self) -> ApiHealthState:
        return self._state

    def update_state(self, state: ApiHealthState) -> None:
        self._state = state
        self._persist()

    def _load(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._state = ApiHealthState()
            return

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except json.JSONDecodeError as exc:
            backup_path = self._backup_corrupted_file()
            self.logger.error(
                log_event(
                    events.HEALTH_STATE_INVALID_JSON,
                    file=str(self.file_path),
                    backup=str(backup_path) if backup_path is not None else None,
                    error=str(exc),
                )
            )
            self._state = ApiHealthState()
            self._persist()
            return
        except OSError as exc:
            self.logger.error(
                log_event(
                    events.HEALTH_STATE_READ_FAILED,
                    file=str(self.file_path),
                    error=str(exc),
                )
            )
            self._state = ApiHealthState()
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
                    events.HEALTH_STATE_BACKUP_FAILED,
                    file=str(self.file_path),
                    error=str(exc),
                )
            )
            return None

    def _normalize_state(self, raw: object) -> tuple[ApiHealthState, bool]:
        if not isinstance(raw, dict):
            return ApiHealthState(), True

        migrated = False
        state_raw = raw
        if "state" in raw:
            maybe_state = raw.get("state")
            if not isinstance(maybe_state, dict):
                return ApiHealthState(), True
            if raw.get("version") != HEALTH_STATE_SCHEMA_VERSION:
                migrated = True
            state_raw = maybe_state
        else:
            migrated = True

        return ApiHealthState.from_dict(state_raw), migrated

    def _persist(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        payload = {
            "version": HEALTH_STATE_SCHEMA_VERSION,
            "state": self._state.to_dict(),
        }
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            temp_path.replace(self.file_path)
        except OSError as exc:
            self.logger.error(
                log_event(
                    events.HEALTH_STATE_PERSIST_FAILED,
                    file=str(self.file_path),
                    temp_file=str(temp_path),
                    error=str(exc),
                )
            )
            raise
