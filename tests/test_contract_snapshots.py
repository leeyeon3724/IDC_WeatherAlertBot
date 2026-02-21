from __future__ import annotations

import argparse
import json
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from app.entrypoints.commands import build_parser
from app.observability import events
from app.settings import Settings
from scripts.event_payload_contract import build_event_payload_contract

CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"


def _load_contract(file_name: str) -> Any:
    path = CONTRACTS_DIR / file_name
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_value(value: Any) -> Any:
    if value is argparse.SUPPRESS:
        return "==SUPPRESS=="
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _current_events_contract() -> dict[str, str]:
    return {
        name: value
        for name, value in sorted(vars(events).items())
        if name.isupper() and isinstance(value, str)
    }


def _current_settings_contract() -> list[dict[str, Any]]:
    contract: list[dict[str, Any]] = []
    for field in fields(Settings):
        has_default = field.default is not MISSING
        default_value = _normalize_value(field.default) if has_default else None
        contract.append(
            {
                "name": field.name,
                "has_default": has_default,
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

    return {
        "default_command": "run",
        "command_names": sorted(subparsers.choices.keys()),
        "commands": commands_contract,
    }


def test_events_contract_snapshot() -> None:
    expected = _load_contract("events_contract.json")
    assert _current_events_contract() == expected


def test_settings_contract_snapshot() -> None:
    expected = _load_contract("settings_contract.json")
    assert _current_settings_contract() == expected


def test_cli_contract_snapshot() -> None:
    expected = _load_contract("cli_contract.json")
    assert _current_cli_contract() == expected


def test_event_payload_contract_snapshot() -> None:
    expected = _load_contract("event_payload_contract.json")
    assert build_event_payload_contract(Path("app")) == expected
