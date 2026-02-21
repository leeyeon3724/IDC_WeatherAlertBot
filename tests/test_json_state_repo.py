from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.models import AlertNotification
from app.repositories.json_state_repo import JsonStateRepository


def test_state_repo_upsert_and_mark_sent(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    repo = JsonStateRepository(state_file)

    notification = AlertNotification(
        event_id="event:109:202602200900:1:발표:정상",
        area_code="11B00000",
        message="테스트 메시지",
        report_url="https://example.com/report",
    )

    assert repo.upsert_notifications([notification]) == 1
    assert repo.pending_count == 1
    unsent = repo.get_unsent("11B00000")
    assert len(unsent) == 1
    assert unsent[0].event_id == notification.event_id

    assert repo.mark_sent(notification.event_id) is True
    assert repo.pending_count == 0

    repo_reloaded = JsonStateRepository(state_file)
    assert repo_reloaded.total_count == 1
    assert repo_reloaded.pending_count == 0


def test_state_repo_migrates_legacy_format(tmp_path) -> None:
    state_file = tmp_path / "legacy.json"
    state_file.write_text(
        json.dumps({"old message A": 1, "old message B": 0}, ensure_ascii=False),
        encoding="utf-8",
    )

    repo = JsonStateRepository(state_file)
    assert repo.total_count == 2
    assert repo.pending_count == 1

    migrated_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert migrated_data.get("version") == 2
    events = migrated_data.get("events", {})
    assert isinstance(events, dict)
    assert all(key.startswith("legacy:") for key in events.keys())


def test_state_repo_recovers_from_corrupted_json(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("{invalid-json", encoding="utf-8")

    repo = JsonStateRepository(state_file)
    assert repo.total_count == 0
    assert repo.pending_count == 0

    recovered_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert recovered_data.get("version") == 2
    assert recovered_data.get("events") == {}
    backups = list(tmp_path.glob("state.json.broken-*"))
    assert len(backups) == 1


def test_state_repo_cleanup_stale_sent_only(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    repo = JsonStateRepository(state_file)

    old_sent = AlertNotification(
        event_id="event:old:1",
        area_code="11B00000",
        message="old sent",
        report_url=None,
    )
    old_unsent = AlertNotification(
        event_id="event:old:2",
        area_code="11B00000",
        message="old unsent",
        report_url=None,
    )
    repo.upsert_notifications([old_sent, old_unsent])
    repo.mark_sent(old_sent.event_id)

    data = json.loads(state_file.read_text(encoding="utf-8"))
    old_time = "2020-01-01T00:00:00Z"
    data["events"][old_sent.event_id]["updated_at"] = old_time
    data["events"][old_sent.event_id]["last_sent_at"] = old_time
    data["events"][old_unsent.event_id]["updated_at"] = old_time
    data["events"][old_unsent.event_id]["first_seen_at"] = old_time
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    repo = JsonStateRepository(state_file)
    removed = repo.cleanup_stale(
        days=30,
        include_unsent=False,
        now=datetime(2026, 2, 21, tzinfo=UTC),
    )
    assert removed == 1
    reloaded = JsonStateRepository(state_file)
    assert reloaded.total_count == 1
    assert reloaded.pending_count == 1


def test_state_repo_cleanup_stale_dry_run(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    repo = JsonStateRepository(state_file)
    repo.upsert_notifications(
        [
            AlertNotification(
                event_id="event:old:3",
                area_code="11B00000",
                message="old sent",
                report_url=None,
            )
        ]
    )
    repo.mark_sent("event:old:3")
    data = json.loads(state_file.read_text(encoding="utf-8"))
    data["events"]["event:old:3"]["updated_at"] = "2020-01-01T00:00:00Z"
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    repo = JsonStateRepository(state_file)
    removed = repo.cleanup_stale(
        days=30,
        dry_run=True,
        now=datetime(2026, 2, 21, tzinfo=UTC),
    )
    assert removed == 1
    unchanged = JsonStateRepository(state_file)
    assert unchanged.total_count == 1


def test_state_repo_cleanup_stale_include_unsent(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    repo = JsonStateRepository(state_file)
    repo.upsert_notifications(
        [
            AlertNotification(
                event_id="event:old:unsent",
                area_code="11B00000",
                message="old unsent",
                report_url=None,
            )
        ]
    )
    data = json.loads(state_file.read_text(encoding="utf-8"))
    data["events"]["event:old:unsent"]["updated_at"] = "2020-01-01T00:00:00Z"
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    repo = JsonStateRepository(state_file)
    removed = repo.cleanup_stale(
        days=30,
        include_unsent=True,
        now=datetime(2026, 2, 21, tzinfo=UTC),
    )
    assert removed == 1
    after = JsonStateRepository(state_file)
    assert after.total_count == 0


def test_state_repo_mark_many_sent(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    repo = JsonStateRepository(state_file)
    repo.upsert_notifications(
        [
            AlertNotification(
                event_id="event:1",
                area_code="11B00000",
                message="msg1",
                report_url=None,
            ),
            AlertNotification(
                event_id="event:2",
                area_code="11B00000",
                message="msg2",
                report_url=None,
            ),
        ]
    )

    marked = repo.mark_many_sent(["event:1", "event:2", "event:3"])
    assert marked == 2
    reloaded = JsonStateRepository(state_file)
    assert reloaded.pending_count == 0


def test_state_repo_logs_read_failure_when_open_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("{}", encoding="utf-8")
    original_open = Path.open

    def _failing_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        if self == state_file and "r" in mode:
            raise OSError("read failed")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _failing_open)

    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.state"):
        repo = JsonStateRepository(state_file)

    assert repo.total_count == 0
    assert any("state.read_failed" in record.message for record in caplog.records)


def test_state_repo_logs_backup_failure_when_replace_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("{invalid-json", encoding="utf-8")
    original_replace = Path.replace

    def _patched_replace(self: Path, target: Path, *args: object, **kwargs: object):
        if self == state_file and ".broken-" in str(target):
            raise OSError("backup failed")
        return original_replace(self, target, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", _patched_replace)

    with caplog.at_level(logging.ERROR, logger="weather_alert_bot.state"):
        repo = JsonStateRepository(state_file)

    assert repo.total_count == 0
    assert any("state.backup_failed" in record.message for record in caplog.records)
    assert any("state.invalid_json" in record.message for record in caplog.records)


def test_state_repo_drops_invalid_records_and_persists(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    payload = {
        "version": 2,
        "events": {
            "event:valid": {
                "area_code": "11B00000",
                "message": "valid",
                "report_url": None,
                "sent": False,
                "first_seen_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
                "last_sent_at": None,
            },
            "event:invalid": "broken",
        },
    }
    state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    repo = JsonStateRepository(state_file)

    assert repo.total_count == 1
    assert repo.get_unsent()[0].event_id == "event:valid"

    rewritten = json.loads(state_file.read_text(encoding="utf-8"))
    assert rewritten["version"] == 2
    assert "event:invalid" not in rewritten["events"]
