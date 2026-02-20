from __future__ import annotations

import json

from app.domain.models import AlertNotification
from app.repositories.state_repo import JsonStateRepository


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
    assert all(key.startswith("legacy:") for key in migrated_data.keys())

