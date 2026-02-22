from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.domain.health import (
    ApiHealthState,
    HealthCycleSample,
    HealthPolicy,
    parse_utc_iso,
    to_utc_iso,
    utc_now,
)


def test_utc_now_returns_aware_utc_datetime() -> None:
    now = utc_now()

    assert now.tzinfo is not None
    assert now.tzinfo == UTC


def test_to_utc_iso_and_parse_roundtrip() -> None:
    source = datetime(2026, 2, 21, 12, 34, 56, tzinfo=ZoneInfo("Asia/Seoul"))

    iso_text = to_utc_iso(source)
    parsed = parse_utc_iso(iso_text)

    assert iso_text == "2026-02-21T03:34:56Z"
    assert parsed == datetime(2026, 2, 21, 3, 34, 56, tzinfo=UTC)


def test_parse_utc_iso_handles_invalid_and_naive_inputs() -> None:
    assert parse_utc_iso(None) is None
    assert parse_utc_iso(123) is None
    assert parse_utc_iso("") is None
    assert parse_utc_iso("not-a-date") is None

    naive = parse_utc_iso("2026-02-21T10:00:00")
    assert naive == datetime(2026, 2, 21, 10, 0, 0, tzinfo=UTC)


def test_health_cycle_sample_from_dict_normalizes_and_filters_fields() -> None:
    sample = HealthCycleSample.from_dict(
        {
            "recorded_at": "2026-02-21T00:00:00Z",
            "total_areas": -1,
            "failed_areas": -3,
            "error_counts": {
                "timeout": 2,
                "invalid_negative": -1,
                "invalid_text": "x",
                123: 5,
            },
            "last_error": "",
        }
    )

    assert sample is not None
    assert sample.total_areas == 0
    assert sample.failed_areas == 0
    assert sample.error_counts == {"timeout": 2}
    assert sample.last_error is None
    assert sample.fail_ratio == 0.0


def test_health_cycle_sample_from_dict_rejects_invalid_shape() -> None:
    assert HealthCycleSample.from_dict("invalid") is None
    assert HealthCycleSample.from_dict({"recorded_at": "invalid"}) is None
    assert (
        HealthCycleSample.from_dict(
            {
                "recorded_at": "2026-02-21T00:00:00Z",
                "total_areas": "4",
                "failed_areas": 1,
            }
        )
        is None
    )


def test_api_health_state_from_dict_normalizes_values() -> None:
    state = ApiHealthState.from_dict(
        {
            "incident_open": 1,
            "incident_started_at": "2026-02-21T00:00:00Z",
            "incident_notified_at": "invalid",
            "last_heartbeat_at": "2026-02-21T01:00:00+00:00",
            "last_recovered_at": "",
            "consecutive_severe_failures": -2,
            "consecutive_stable_successes": 3,
            "incident_total_cycles": -1,
            "incident_failed_cycles": 4,
            "incident_error_counts": {"timeout": 5, "bad": -1, 123: 1},
            "recovery_backfill_pending_start_date": "20260218",
            "recovery_backfill_pending_end_date": "invalid",
            "recent_cycles": [
                {
                    "recorded_at": "2026-02-21T00:00:00Z",
                    "total_areas": 4,
                    "failed_areas": 2,
                    "error_counts": {"timeout": 2},
                    "last_error": "timeout",
                },
                {"recorded_at": "invalid"},
            ],
        }
    )

    assert state.incident_open is True
    assert state.incident_started_at == datetime(2026, 2, 21, 0, 0, tzinfo=UTC)
    assert state.incident_notified_at is None
    assert state.last_heartbeat_at == datetime(2026, 2, 21, 1, 0, tzinfo=UTC)
    assert state.last_recovered_at is None
    assert state.consecutive_severe_failures == 0
    assert state.consecutive_stable_successes == 3
    assert state.incident_total_cycles == 0
    assert state.incident_failed_cycles == 4
    assert state.incident_error_counts == {"timeout": 5}
    assert state.recovery_backfill_pending_start_date == "20260218"
    assert state.recovery_backfill_pending_end_date is None
    assert len(state.recent_cycles) == 1


def test_api_health_state_trim_and_window_behaviour() -> None:
    now = datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
    state = ApiHealthState()
    state = state.append_cycle(
        HealthCycleSample(
            recorded_at=now,
            total_areas=4,
            failed_areas=1,
            error_counts={},
        )
    )
    state = state.append_cycle(
        HealthCycleSample(
            recorded_at=now.replace(hour=11, minute=58),
            total_areas=4,
            failed_areas=0,
            error_counts={},
        )
    )

    assert len(state.cycles_in_window(now=now, window_sec=0)) == 0
    assert len(state.cycles_in_window(now=now, window_sec=180)) == 2

    state = state.trim_recent_cycles(now=now, retention_sec=90)
    assert len(state.recent_cycles) == 1

    state = state.trim_recent_cycles(now=now, retention_sec=0)
    assert state.recent_cycles == []


def test_health_policy_max_window_sec() -> None:
    policy = HealthPolicy(outage_window_sec=100, recovery_window_sec=200)
    assert policy.max_window_sec() == 200
