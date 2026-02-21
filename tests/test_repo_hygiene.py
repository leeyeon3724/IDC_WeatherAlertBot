from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.check_repo_hygiene import build_report


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_repo_fixture(repo_root: Path) -> None:
    _write(
        repo_root / "app" / "settings.py",
        """
        SERVICE_KEY = "ignored"
        os.getenv("SERVICE_API_KEY")
        os.getenv("SERVICE_HOOK_URL")
        _parse_json_env("AREA_CODES", "[]", list)
        _parse_json_env("AREA_CODE_MAPPING", "{}", dict)
        """,
    )
    _write(
        repo_root / ".env.example",
        """
        SERVICE_API_KEY=test
        SERVICE_HOOK_URL=https://hook.example
        AREA_CODES=["L1012000"]
        AREA_CODE_MAPPING={"L1012000":"판교"}
        """,
    )
    _write(
        repo_root / ".env.live-e2e.example",
        """
        ENABLE_LIVE_E2E=true
        SERVICE_API_KEY=test-live
        SERVICE_HOOK_URL=https://hook.example/live
        AREA_CODES=["L1090000"]
        AREA_CODE_MAPPING={"L1090000":"서울"}
        """,
    )
    _write(
        repo_root / "README.md",
        """
        - `docs/SETUP.md`: setup
        - `docs/OPERATION.md`: operation
        - `docs/EVENTS.md`: events
        - `docs/TESTING.md`: testing
        - `docs/BACKLOG.md`: backlog
        """,
    )
    for file_name in ["SETUP.md", "OPERATION.md", "EVENTS.md", "TESTING.md", "BACKLOG.md"]:
        _write(repo_root / "docs" / file_name, "# doc")


def test_build_report_passes_for_compact_repo_fixture(tmp_path: Path) -> None:
    _build_repo_fixture(tmp_path)

    report = build_report(tmp_path)

    assert report["passed"] is True
    assert report["missing_required_docs"] == []
    assert report["unknown_docs"] == []
    assert report["legacy_docs_present"] == []
    assert report["missing_in_env_example"] == []
    assert report["unknown_in_env_example"] == []
    assert report["live_e2e_example_exists"] is True
    assert report["missing_in_live_e2e_example"] == []
    assert report["unknown_in_live_e2e_example"] == []
    assert report["invalid_live_e2e_json"] == []
    assert report["missing_in_readme_doc_map"] == []
    assert report["unknown_in_readme_doc_map"] == []


def test_build_report_detects_hygiene_violations(tmp_path: Path) -> None:
    _build_repo_fixture(tmp_path)
    _write(tmp_path / "docs" / "EXTRA.md", "# extra")
    _write(tmp_path / "docs" / "REFRACTORING_BACKLOG.md", "# legacy")
    _write(
        tmp_path / ".env.example",
        """
        SERVICE_API_KEY=test
        AREA_CODES=["L1012000"]
        AREA_CODE_MAPPING={"L1012000":"판교"}
        UNUSED_KEY=extra
        """,
    )
    _write(
        tmp_path / "README.md",
        """
        - `docs/SETUP.md`: setup
        - `docs/OPERATION.md`: operation
        - `docs/EVENTS.md`: events
        - `docs/TESTING.md`: testing
        """,
    )
    _write(
        tmp_path / ".env.live-e2e.example",
        """
        ENABLE_LIVE_E2E=true
        SERVICE_API_KEY=test-live
        AREA_CODES=[L1090000]
        AREA_CODE_MAPPING={"L1090000":"서울"}
        UNKNOWN_LIVE_E2E_KEY=yes
        """,
    )

    report = build_report(tmp_path)

    assert report["passed"] is False
    assert report["unknown_docs"] == ["EXTRA.md", "REFRACTORING_BACKLOG.md"]
    assert report["legacy_docs_present"] == ["REFRACTORING_BACKLOG.md"]
    assert report["missing_in_env_example"] == ["SERVICE_HOOK_URL"]
    assert report["unknown_in_env_example"] == ["UNUSED_KEY"]
    assert report["missing_in_live_e2e_example"] == ["SERVICE_HOOK_URL"]
    assert report["unknown_in_live_e2e_example"] == ["UNKNOWN_LIVE_E2E_KEY"]
    assert report["invalid_live_e2e_json"] == ["AREA_CODES:invalid_json"]
    assert report["missing_in_readme_doc_map"] == ["BACKLOG.md"]
