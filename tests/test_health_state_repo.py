from __future__ import annotations

import json
from datetime import UTC, datetime

from app.domain.health import ApiHealthState, HealthCycleSample
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


def test_health_state_repo_recovers_from_corrupted_json(tmp_path) -> None:
    state_file = tmp_path / "health_state.json"
    state_file.write_text("{invalid-json", encoding="utf-8")

    repo = JsonHealthStateRepository(state_file)
    assert repo.state.incident_open is False
    assert repo.state.incident_total_cycles == 0

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload.get("version") == 1
    assert payload.get("state", {}).get("incident_open") is False
    backups = list(tmp_path.glob("health_state.json.broken-*"))
    assert len(backups) == 1
