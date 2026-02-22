from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.alert_rules import (
    DEFAULT_ALERT_RULES_FILE,
    AlertRulesError,
    default_alert_rules,
    load_alert_rules,
)


def _write_rules_file(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "alert_rules.test.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_load_alert_rules_default_schema_file() -> None:
    rules = load_alert_rules(DEFAULT_ALERT_RULES_FILE)

    assert rules.schema_version == 1
    assert rules.unmapped_code_policy == "fallback"
    assert rules.code_maps.warn_var["2"] == "호우"
    assert rules.message_rules.publish_command_value == "발표"


def test_load_alert_rules_v2_schema_file() -> None:
    rules = load_alert_rules(Path("config/alert_rules.v2.json"))

    assert rules.schema_version == 2
    assert rules.unmapped_code_policy == "fallback"
    assert rules.code_maps.warn_var["2"] == "호우"
    assert rules.code_maps.command["1"] == "발표"
    assert "{command}" in rules.message_rules.release_or_update_template


def test_default_alert_rules_returns_independent_mapping_objects() -> None:
    first = default_alert_rules()
    second = default_alert_rules()

    first.code_maps.warn_var["2"] = "임시"
    assert second.code_maps.warn_var["2"] == "호우"


def test_load_alert_rules_rejects_unknown_unmapped_policy(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_ALERT_RULES_FILE.read_text(encoding="utf-8"))
    payload["unmapped_code_policy"] = "warn_only"
    rules_file = _write_rules_file(tmp_path, payload)

    with pytest.raises(AlertRulesError, match="unmapped_code_policy"):
        load_alert_rules(rules_file)


def test_load_alert_rules_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_ALERT_RULES_FILE.read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    rules_file = _write_rules_file(tmp_path, payload)

    with pytest.raises(AlertRulesError, match="unsupported schema_version"):
        load_alert_rules(rules_file)


def test_load_alert_rules_rejects_invalid_template_placeholders(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_ALERT_RULES_FILE.read_text(encoding="utf-8"))
    payload["message_rules"]["publish_template"] = "{time} {unknown}"
    rules_file = _write_rules_file(tmp_path, payload)

    with pytest.raises(AlertRulesError, match="unsupported placeholder"):
        load_alert_rules(rules_file)


def test_load_alert_rules_rejects_missing_required_template_placeholders(tmp_path: Path) -> None:
    payload = json.loads(DEFAULT_ALERT_RULES_FILE.read_text(encoding="utf-8"))
    payload["message_rules"]["release_or_update_template"] = "{time} {area_name} {command}"
    rules_file = _write_rules_file(tmp_path, payload)

    with pytest.raises(AlertRulesError, match="missing required placeholders"):
        load_alert_rules(rules_file)


def test_load_alert_rules_v2_rejects_missing_mappings_key(tmp_path: Path) -> None:
    payload = json.loads(Path("config/alert_rules.v2.json").read_text(encoding="utf-8"))
    del payload["mappings"]["warning_level"]
    rules_file = _write_rules_file(tmp_path, payload)

    with pytest.raises(AlertRulesError, match="mappings.warning_level"):
        load_alert_rules(rules_file)
