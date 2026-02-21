from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.check_area_mapping_sync import build_report


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_build_report_passes_when_area_codes_are_fully_mapped(tmp_path: Path) -> None:
    _write(
        tmp_path / ".env.example",
        """
        AREA_CODES=["L1012000","L1012100"]
        AREA_CODE_MAPPING={"L1012000":"판교","L1012100":"평촌"}
        """,
    )
    _write(
        tmp_path / ".env.live-e2e.example",
        """
        AREA_CODES=["L1090000"]
        AREA_CODE_MAPPING={"L1090000":"서울"}
        """,
    )

    report = build_report(tmp_path)

    assert report["passed"] is True
    assert report["missing_or_invalid"] == []
    assert report["mapping_gaps"] == []


def test_build_report_fails_when_area_code_mapping_has_gaps(tmp_path: Path) -> None:
    _write(
        tmp_path / ".env.example",
        """
        AREA_CODES=["L1012000","L1012100"]
        AREA_CODE_MAPPING={"L1012000":"판교"}
        """,
    )
    _write(
        tmp_path / ".env.live-e2e.example",
        """
        AREA_CODES=["L1090000"]
        AREA_CODE_MAPPING={"L1090000":"서울"}
        """,
    )

    report = build_report(tmp_path)

    assert report["passed"] is False
    assert report["mapping_gaps"] == [
        {
            "file": (tmp_path / ".env.example").as_posix(),
            "missing_mapping_keys": ["L1012100"],
        }
    ]


def test_build_report_fails_for_invalid_or_missing_files(tmp_path: Path) -> None:
    _write(
        tmp_path / ".env.example",
        """
        AREA_CODES=[L1012000]
        AREA_CODE_MAPPING={"L1012000":"판교"}
        """,
    )

    report = build_report(tmp_path)

    assert report["passed"] is False
    assert {
        "file": (tmp_path / ".env.example").as_posix(),
        "errors": ["AREA_CODES:invalid_json"],
    } in report["missing_or_invalid"]
    assert {
        "file": (tmp_path / ".env.live-e2e.example").as_posix(),
        "errors": ["file:missing"],
    } in report["missing_or_invalid"]
