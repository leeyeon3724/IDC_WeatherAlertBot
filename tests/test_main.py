from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.entrypoints import cli as entrypoint
from app.settings import Settings, SettingsError
from tests.main_test_harness import make_settings


def test_run_service_returns_1_on_invalid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("test.main.invalid")
    monkeypatch.setattr(entrypoint, "setup_logging", lambda *args, **kwargs: logger)

    def _raise_settings(cls, env_file: str | None = ".env") -> Settings:
        raise SettingsError("invalid settings")

    monkeypatch.setattr(entrypoint.Settings, "from_env", classmethod(_raise_settings))

    assert entrypoint._run_service() == 1


def test_cleanup_state_command_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_cleanup_state(
        *,
        state_repository_type: str | None,
        json_state_file: str,
        sqlite_state_file: str,
        days: int,
        include_unsent: bool,
        dry_run: bool,
    ) -> int:
        captured.update(
            {
                "state_repository_type": state_repository_type,
                "json_state_file": json_state_file,
                "sqlite_state_file": sqlite_state_file,
                "days": days,
                "include_unsent": include_unsent,
                "dry_run": dry_run,
            }
        )
        return 0

    monkeypatch.setattr(entrypoint, "_cleanup_state", _fake_cleanup_state)

    result = entrypoint.main(
        [
            "cleanup-state",
            "--state-repository-type",
            "json",
            "--json-state-file",
            "tmp/state.json",
            "--sqlite-state-file",
            "tmp/state.db",
            "--days",
            "5",
            "--include-unsent",
            "--dry-run",
        ]
    )

    assert result == 0
    assert captured == {
        "state_repository_type": "json",
        "json_state_file": "tmp/state.json",
        "sqlite_state_file": "tmp/state.db",
        "days": 5,
        "include_unsent": True,
        "dry_run": True,
    }


def test_migrate_state_command_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_migrate_state(json_state_file: str, sqlite_state_file: str) -> int:
        captured.update(
            {
                "json_state_file": json_state_file,
                "sqlite_state_file": sqlite_state_file,
            }
        )
        return 0

    monkeypatch.setattr(entrypoint, "_migrate_state", _fake_migrate_state)

    result = entrypoint.main(
        [
            "migrate-state",
            "--json-state-file",
            "tmp/source.json",
            "--sqlite-state-file",
            "tmp/target.db",
        ]
    )

    assert result == 0
    assert captured == {
        "json_state_file": "tmp/source.json",
        "sqlite_state_file": "tmp/target.db",
    }


def test_verify_state_command_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_verify_state(json_state_file: str, sqlite_state_file: str, strict: bool) -> int:
        captured.update(
            {
                "json_state_file": json_state_file,
                "sqlite_state_file": sqlite_state_file,
                "strict": strict,
            }
        )
        return 0

    monkeypatch.setattr(entrypoint, "_verify_state", _fake_verify_state)

    result = entrypoint.main(
        [
            "verify-state",
            "--json-state-file",
            "tmp/source.json",
            "--sqlite-state-file",
            "tmp/target.db",
            "--strict",
        ]
    )

    assert result == 0
    assert captured == {
        "json_state_file": "tmp/source.json",
        "sqlite_state_file": "tmp/target.db",
        "strict": True,
    }


def test_cleanup_state_rejects_negative_days() -> None:
    with pytest.raises(SystemExit) as exc:
        entrypoint.main(["cleanup-state", "--days", "-1"])
    assert exc.value.code == 2


def test_cleanup_state_uses_repository_type_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_cleanup_state(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setenv("STATE_REPOSITORY_TYPE", "sqlite")
    monkeypatch.setenv("SQLITE_STATE_FILE", "tmp/clean.db")
    monkeypatch.setattr(entrypoint.commands, "cleanup_state", _fake_cleanup_state)

    result = entrypoint._cleanup_state(
        state_repository_type=None,
        json_state_file="tmp/state.json",
        sqlite_state_file="tmp/clean.db",
        days=7,
        include_unsent=True,
        dry_run=True,
    )

    assert result == 0
    assert captured["state_repository_type"] == "sqlite"
    assert captured["sqlite_state_file"] == "tmp/clean.db"
    assert captured["json_state_file"] == "tmp/state.json"
    assert captured["days"] == 7
    assert captured["include_unsent"] is True
    assert captured["dry_run"] is True


def test_default_command_routes_to_run_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entrypoint, "_run_service", lambda: 7)
    assert entrypoint.main([]) == 7
    assert entrypoint.main(["run"]) == 7


def test_build_state_repository_defaults_to_sqlite(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    logger = logging.getLogger("test.main.repo_factory.sqlite.default")

    repo = entrypoint._build_state_repository(settings=settings, logger=logger)

    assert repo.__class__.__name__ == "SqliteStateRepository"


def test_build_state_repository_uses_sqlite_when_configured(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        state_repository_type="sqlite",
        sqlite_state_file=tmp_path / "state.db",
    )
    logger = logging.getLogger("test.main.repo_factory.sqlite")

    repo = entrypoint._build_state_repository(settings=settings, logger=logger)

    assert repo.__class__.__name__ == "SqliteStateRepository"


def test_build_state_repository_uses_json_when_configured(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        state_repository_type="json",
        sent_messages_file=tmp_path / "state.json",
    )
    logger = logging.getLogger("test.main.repo_factory.json")

    repo = entrypoint._build_state_repository(settings=settings, logger=logger)

    assert repo.__class__.__name__ == "JsonStateRepository"
