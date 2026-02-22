from __future__ import annotations

import argparse
import difflib
import json
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.entrypoints import cli as entrypoint
from app.entrypoints.commands import build_parser
from app.observability import events
from app.settings import Settings
from scripts.event_payload_contract import build_event_payload_contract

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
PROJECT_ROOT = CONTRACTS_DIR.parent.parent


def _load_contract(file_name: str) -> Any:
    path = CONTRACTS_DIR / file_name
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_value(value: Any) -> Any:
    if value is argparse.SUPPRESS:
        return "==SUPPRESS=="
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _normalize_annotation(annotation: Any) -> str:
    if isinstance(annotation, str):
        return annotation
    if hasattr(annotation, "__name__"):
        return str(annotation.__name__)
    return str(annotation).replace("typing.", "")


def _assert_snapshot_matches(*, name: str, current: Any, expected: Any) -> None:
    if current == expected:
        return
    current_text = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True)
    expected_text = json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True)
    diff = "\n".join(
        difflib.unified_diff(
            expected_text.splitlines(),
            current_text.splitlines(),
            fromfile=f"{name}:expected",
            tofile=f"{name}:current",
            lineterm="",
        )
    )
    raise AssertionError(f"{name} snapshot mismatch\n{diff}")


def _current_events_contract() -> dict[str, str]:
    return {
        name: value
        for name, value in sorted(vars(events).items())
        if name.isupper() and isinstance(value, str)
    }


def _event_payload_source_root() -> Path:
    return PROJECT_ROOT / "app"


def _current_event_payload_contract() -> dict[str, list[str]]:
    return build_event_payload_contract(_event_payload_source_root())


def _current_settings_contract() -> list[dict[str, Any]]:
    contract: list[dict[str, Any]] = []
    for field in fields(Settings):
        has_default = field.default is not MISSING
        has_default_factory = field.default_factory is not MISSING
        default_value = _normalize_value(field.default) if has_default else None
        contract.append(
            {
                "name": field.name,
                "annotation": _normalize_annotation(field.type),
                "required": not has_default and not has_default_factory,
                "has_default": has_default,
                "has_default_factory": has_default_factory,
                "default": default_value,
            }
        )
    return contract


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("parser must define subcommands")


def _command_options(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for action in parser._actions:
        if not action.option_strings:
            continue
        options.append(
            {
                "flags": action.option_strings,
                "dest": action.dest,
                "required": action.required,
                "default": _normalize_value(action.default),
            }
        )
    return options


def _current_cli_contract() -> dict[str, Any]:
    parser = build_parser()
    subparsers = _subparsers_action(parser)
    commands_contract: dict[str, Any] = {}

    for name, subparser in sorted(subparsers.choices.items()):
        commands_contract[name] = {
            "options": _command_options(subparser),
            "parse_defaults": vars(subparser.parse_args([])),
        }

    with patch.object(entrypoint, "_run_service", return_value=71):
        default_command = "run" if entrypoint.main([]) == 71 else "unknown"

    return {
        "default_command": default_command,
        "command_names": sorted(subparsers.choices.keys()),
        "commands": commands_contract,
    }


def test_events_contract_snapshot() -> None:
    expected = _load_contract("events_contract.json")
    _assert_snapshot_matches(
        name="events_contract.json",
        current=_current_events_contract(),
        expected=expected,
    )


def test_settings_contract_snapshot() -> None:
    expected = _load_contract("settings_contract.json")
    _assert_snapshot_matches(
        name="settings_contract.json",
        current=_current_settings_contract(),
        expected=expected,
    )


def test_cli_contract_snapshot() -> None:
    expected = _load_contract("cli_contract.json")
    _assert_snapshot_matches(
        name="cli_contract.json",
        current=_current_cli_contract(),
        expected=expected,
    )


def test_event_payload_contract_snapshot() -> None:
    expected = _load_contract("event_payload_contract.json")
    _assert_snapshot_matches(
        name="event_payload_contract.json",
        current=_current_event_payload_contract(),
        expected=expected,
    )


def test_event_payload_contract_snapshot_is_cwd_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _load_contract("event_payload_contract.json")
    monkeypatch.chdir(CONTRACTS_DIR.parent)
    assert _current_event_payload_contract() == expected
