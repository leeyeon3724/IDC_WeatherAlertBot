from __future__ import annotations

from datetime import UTC, datetime

from app.repositories.state_models import parse_iso_to_utc, utc_now_iso


def test_utc_now_iso_returns_utc_z_suffix() -> None:
    value = utc_now_iso()
    assert value.endswith("Z")
    parsed = parse_iso_to_utc(value)
    assert parsed is not None
    assert parsed.tzinfo == UTC


def test_parse_iso_to_utc_handles_z_and_offset() -> None:
    zulu = parse_iso_to_utc("2026-02-21T12:00:00Z")
    offset = parse_iso_to_utc("2026-02-21T21:00:00+09:00")

    assert zulu is not None
    assert offset is not None
    assert zulu == offset


def test_parse_iso_to_utc_invalid_values() -> None:
    assert parse_iso_to_utc(None) is None
    assert parse_iso_to_utc(123) is None
    assert parse_iso_to_utc("") is None
    assert parse_iso_to_utc("invalid") is None


def test_parse_iso_to_utc_naive_datetime_assumes_utc() -> None:
    parsed = parse_iso_to_utc("2026-02-21T12:00:00")

    assert parsed is not None
    assert parsed == datetime(2026, 2, 21, 12, 0, tzinfo=UTC)
