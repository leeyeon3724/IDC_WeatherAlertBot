from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.health import ApiHealthDecision
from app.entrypoints import cli as entrypoint
from app.usecases.process_cycle import CycleStats
from tests.main_test_harness import make_settings, patch_service_runtime


def test_patch_service_runtime_applies_fake_runtime_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    probe = patch_service_runtime(
        monkeypatch=monkeypatch,
        settings=settings,
        logger_name="test.main.harness.apply",
        cycle_stats=CycleStats(
            start_date="20260221",
            end_date="20260222",
            area_count=1,
        ),
        health_decision=ApiHealthDecision(incident_open=False),
    )

    result = entrypoint._run_service()

    assert result == 0
    assert probe.processor_lookback_calls == [None]
    assert probe.state_repo_kinds == ["sqlite"]
    assert probe.sqlite_repo_file == settings.sqlite_state_file
