from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.health import ApiHealthState, HealthCycleSample
from app.observability import events
from app.repositories.health_state_repo import JsonHealthStateRepository


def test_health_state_repo_roundtrip(tmp_path) -> None:
    state_file = tmp_path / "health_state.json"
    repo = JsonHealthStateRepository(state_file)

    state = ApiHealthState(
        incident_open=True,
        incident_started_at=datetime(2026, 2, 21, 0, 0, tzinfo=UTC),
        consecutive_severe_failures=4,
        incident_total_cycles=7,
        incident_failed_cycles=7,
        incident_error_counts={"timeout": 7},
        recent_cycles=[
            HealthCycleSample(
                recorded_at=datetime(2026, 2, 21, 0, 0, tzinfo=UTC),
                total_areas=4,
                failed_areas=4,
                error_counts={"timeout": 4},
                last_error="timeout",
            )
        ],
    )
    repo.update_state(state)

    reloaded = JsonHealthStateRepository(state_file)
    assert reloaded.state.incident_open is True
    assert reloaded.state.consecutive_severe_failures == 4
    assert reloaded.state.incident_total_cycles == 7
    assert reloaded.state.incident_error_counts["timeout"] == 7
    assert len(reloaded.state.recent_cycles) == 1


def test_health_state_repo_recovers_from_corrupted_json(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "health_state.json"
    state_file.write_text("{invalid-json", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.health_state"):
        repo = JsonHealthStateRepository(state_file)
    assert repo.state.incident_open is False
    assert repo.state.incident_total_cycles == 0

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert payload.get("state", {}).get("incident_open") is False
    backups = list(tmp_path.glob("health_state.json.broken-*"))
    assert len(backups) == 1
    assert any(events.HEALTH_STATE_INVALID_JSON in record.message for record in caplog.records)


def test_health_state_repo_logs_read_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "health_state.json"
    state_file.write_text("{}", encoding="utf-8")

    original_open = Path.open

    def _failing_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        if self == state_file and "r" in mode:
            raise OSError("read failed")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _failing_open)

    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.health_state"):
        JsonHealthStateRepository(state_file)

    assert any(events.HEALTH_STATE_READ_FAILED in record.message for record in caplog.records)


def test_health_state_repo_logs_backup_failure_when_replace_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "health_state.json"
    state_file.write_text("{invalid-json", encoding="utf-8")
    original_replace = Path.replace

    def _patched_replace(self: Path, target: Path, *args: object, **kwargs: object):
        if self == state_file and ".broken-" in str(target):
            raise OSError("backup failed")
        return original_replace(self, target, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", _patched_replace)

    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.health_state"):
        repo = JsonHealthStateRepository(state_file)

    assert repo.state.incident_open is False
    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(payload.get("event") == events.HEALTH_STATE_BACKUP_FAILED for payload in payloads)
    assert any(payload.get("event") == events.HEALTH_STATE_INVALID_JSON for payload in payloads)


def test_health_state_repo_logs_persist_failure_when_write_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "health_state.json"
    temp_file = state_file.with_suffix(".json.tmp")
    repo = JsonHealthStateRepository(state_file)
    original_open = Path.open

    def _failing_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        if self == temp_file and "w" in mode:
            raise OSError("persist failed")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _failing_open)
    state = ApiHealthState(incident_open=True)

    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.health_state"):
        with pytest.raises(OSError, match="persist failed"):
            repo.update_state(state)

    payloads = [json.loads(record.message) for record in caplog.records]
    assert any(payload.get("event") == events.HEALTH_STATE_PERSIST_FAILED for payload in payloads)
