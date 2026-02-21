from __future__ import annotations

from pathlib import Path

from scripts.soak_report import run_soak


def test_run_soak_passes_with_stable_pattern(tmp_path: Path) -> None:
    report = run_soak(
        cycles=20,
        area_count=2,
        new_event_every=0,
        notifier_fail_every=0,
        state_file=tmp_path / "state.json",
        max_pending=0,
        max_duplicate_deliveries=0,
        max_state_growth=0,
        max_memory_growth_kib=4096,
    )

    assert report["passed"] is True
    assert report["duplicate_delivery_count"] == 0
    assert report["notification_failures"] == 0


def test_run_soak_fails_when_state_growth_exceeds_budget(tmp_path: Path) -> None:
    report = run_soak(
        cycles=30,
        area_count=2,
        new_event_every=5,
        notifier_fail_every=0,
        state_file=tmp_path / "state.json",
        max_pending=0,
        max_duplicate_deliveries=0,
        max_state_growth=0,
        max_memory_growth_kib=4096,
    )

    assert report["passed"] is False
    assert any("state_growth exceeded budget" in reason for reason in report["failed_reasons"])


def test_run_soak_fails_on_synthetic_notifier_failures(tmp_path: Path) -> None:
    report = run_soak(
        cycles=20,
        area_count=2,
        new_event_every=0,
        notifier_fail_every=2,
        state_file=tmp_path / "state.json",
        max_pending=0,
        max_duplicate_deliveries=0,
        max_state_growth=0,
        max_memory_growth_kib=4096,
    )

    assert report["passed"] is False
    assert report["notification_failures"] > 0
