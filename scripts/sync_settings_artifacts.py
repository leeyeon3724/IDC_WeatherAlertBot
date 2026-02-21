from __future__ import annotations

import argparse
import difflib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path

from app.domain.alert_rules import DEFAULT_ALERT_RULES_FILE
from app.settings import (
    DEFAULT_WEATHER_API_ALLOWED_HOSTS,
    DEFAULT_WEATHER_API_ALLOWED_PATH_PREFIXES,
    Settings,
)

ENV_EXAMPLE_REQUIRED_KEYS = [
    "SERVICE_API_KEY",
    "SERVICE_HOOK_URL",
    "AREA_CODES",
    "AREA_CODE_MAPPING",
]
ENV_EXAMPLE_OPTIONAL_KEYS = [
    "WEATHER_ALERT_DATA_API_URL",
    "WEATHER_API_WARNING_TYPE",
    "WEATHER_API_STATION_ID",
    "WEATHER_API_ALLOWED_HOSTS",
    "WEATHER_API_ALLOWED_PATH_PREFIXES",
    "ALERT_RULES_FILE",
    "SENT_MESSAGES_FILE",
    "STATE_REPOSITORY_TYPE",
    "SQLITE_STATE_FILE",
    "REQUEST_TIMEOUT_SEC",
    "REQUEST_CONNECT_TIMEOUT_SEC",
    "REQUEST_READ_TIMEOUT_SEC",
    "MAX_RETRIES",
    "RETRY_DELAY_SEC",
    "API_SOFT_RATE_LIMIT_PER_SEC",
    "NOTIFIER_TIMEOUT_SEC",
    "NOTIFIER_CONNECT_TIMEOUT_SEC",
    "NOTIFIER_READ_TIMEOUT_SEC",
    "NOTIFIER_MAX_RETRIES",
    "NOTIFIER_RETRY_DELAY_SEC",
    "NOTIFIER_SEND_RATE_LIMIT_PER_SEC",
    "NOTIFIER_MAX_ATTEMPTS_PER_CYCLE",
    "NOTIFIER_CIRCUIT_BREAKER_ENABLED",
    "NOTIFIER_CIRCUIT_FAILURE_THRESHOLD",
    "NOTIFIER_CIRCUIT_RESET_SEC",
    "AREA_MAX_WORKERS",
    "LOOKBACK_DAYS",
    "CYCLE_INTERVAL_SEC",
    "SHUTDOWN_TIMEOUT_SEC",
    "AREA_INTERVAL_SEC",
    "CLEANUP_ENABLED",
    "CLEANUP_RETENTION_DAYS",
    "CLEANUP_INCLUDE_UNSENT",
    "BOT_NAME",
    "TIMEZONE",
    "LOG_LEVEL",
    "DRY_RUN",
    "RUN_ONCE",
    "HEALTH_ALERT_ENABLED",
    "HEALTH_OUTAGE_WINDOW_SEC",
    "HEALTH_OUTAGE_FAIL_RATIO_THRESHOLD",
    "HEALTH_OUTAGE_MIN_FAILED_CYCLES",
    "HEALTH_OUTAGE_CONSECUTIVE_FAILURES",
    "HEALTH_RECOVERY_WINDOW_SEC",
    "HEALTH_RECOVERY_MAX_FAIL_RATIO",
    "HEALTH_RECOVERY_CONSECUTIVE_SUCCESSES",
    "HEALTH_HEARTBEAT_INTERVAL_SEC",
    "HEALTH_BACKOFF_MAX_SEC",
    "HEALTH_RECOVERY_BACKFILL_MAX_DAYS",
    "HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS",
    "HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE",
    "HEALTH_STATE_FILE",
]
ENV_EXAMPLE_ALL_KEYS = ENV_EXAMPLE_REQUIRED_KEYS + ENV_EXAMPLE_OPTIONAL_KEYS

ENV_EXAMPLE_PLACEHOLDERS = {
    "SERVICE_API_KEY": "YOUR_SERVICE_KEY",
    "SERVICE_HOOK_URL": "https://hook.dooray.com/services/your/path",
    "AREA_CODES": "[\"L1012000\",\"L1012100\",\"L1070100\",\"L1050100\"]",
    "AREA_CODE_MAPPING": (
        "{\"L1012000\":\"판교(성남)\",\"L1012100\":\"평촌(안양)\",\"L1070100\":\"대구\","
        "\"L1050100\":\"광주\"}"
    ),
}

LIVE_E2E_KEYS = [
    "ENABLE_LIVE_E2E",
    "SERVICE_API_KEY",
    "SERVICE_HOOK_URL",
    "AREA_CODES",
    "AREA_CODE_MAPPING",
    "RUN_ONCE",
    "DRY_RUN",
    "LOOKBACK_DAYS",
    "HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS",
    "HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE",
    "CYCLE_INTERVAL_SEC",
    "SHUTDOWN_TIMEOUT_SEC",
    "AREA_INTERVAL_SEC",
    "API_SOFT_RATE_LIMIT_PER_SEC",
    "NOTIFIER_SEND_RATE_LIMIT_PER_SEC",
    "LOG_LEVEL",
    "TIMEZONE",
    "ALERT_RULES_FILE",
    "SENT_MESSAGES_FILE",
    "HEALTH_STATE_FILE",
    "SQLITE_STATE_FILE",
    "STATE_REPOSITORY_TYPE",
]

LIVE_E2E_OVERRIDES = {
    "ENABLE_LIVE_E2E": "true",
    "SERVICE_API_KEY": "YOUR_TEST_SERVICE_KEY",
    "SERVICE_HOOK_URL": "https://hook.dooray.com/services/your/test/path",
    "AREA_CODES": "[\"L1090000\"]",
    "AREA_CODE_MAPPING": "{\"L1090000\":\"서울\"}",
    "RUN_ONCE": "true",
    "DRY_RUN": "false",
    "LOOKBACK_DAYS": "0",
    "HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS": "1",
    "HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE": "3",
    "CYCLE_INTERVAL_SEC": "0",
    "AREA_INTERVAL_SEC": "0",
    "SENT_MESSAGES_FILE": "./artifacts/live-e2e/local/sent_messages.live-e2e.json",
    "HEALTH_STATE_FILE": "./artifacts/live-e2e/local/api_health_state.live-e2e.json",
    "SQLITE_STATE_FILE": "./artifacts/live-e2e/local/sent_messages.live-e2e.db",
}

SETUP_MARKER_START = "<!-- SETTINGS_DEFAULTS_TABLE:START -->"
SETUP_MARKER_END = "<!-- SETTINGS_DEFAULTS_TABLE:END -->"
SETUP_INSERT_BEFORE = "## 5. 로컬 실행"
SETUP_SECTION_HEADING = "### 4.2 선택 환경변수 기본값(자동 생성)"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _to_env_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        text = value.as_posix()
        if text.startswith(("/", "./")):
            return text
        return f"./{text}"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


@contextmanager
def _isolated_environment(keys: list[str]) -> Iterator[None]:
    before = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _to_project_relative_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return _to_env_string(path)
    return f"./{rel.as_posix()}"


def build_settings_env_defaults() -> dict[str, str]:
    keys_to_control = sorted(
        set(ENV_EXAMPLE_ALL_KEYS)
        | {
            "ALERT_RULES_FILE",
            "WEATHER_API_ALLOWED_HOSTS",
            "WEATHER_API_ALLOWED_PATH_PREFIXES",
        }
    )
    bootstrap_required_env = {
        "SERVICE_API_KEY": "DUMMY_SERVICE_KEY",
        "SERVICE_HOOK_URL": "https://hook.dooray.com/services/dummy/path",
        "AREA_CODES": "[\"L1090000\"]",
        "AREA_CODE_MAPPING": "{\"L1090000\":\"서울\"}",
    }
    with _isolated_environment(keys_to_control):
        for key, value in bootstrap_required_env.items():
            os.environ[key] = value
        settings = Settings.from_env(env_file=None)

    defaults: dict[str, str] = {}
    for field in fields(Settings):
        env_key = field.name.upper()
        if env_key in ENV_EXAMPLE_ALL_KEYS:
            defaults[env_key] = _to_env_string(getattr(settings, field.name))

    defaults["WEATHER_API_ALLOWED_HOSTS"] = _to_env_string(DEFAULT_WEATHER_API_ALLOWED_HOSTS)
    defaults["WEATHER_API_ALLOWED_PATH_PREFIXES"] = _to_env_string(
        DEFAULT_WEATHER_API_ALLOWED_PATH_PREFIXES
    )
    defaults["ALERT_RULES_FILE"] = _to_project_relative_path(DEFAULT_ALERT_RULES_FILE)
    return defaults


def render_env_example(defaults: dict[str, str]) -> str:
    lines = [
        "# Required",
        "# Use raw(decoded) key value. Do not pre-URL-encode.",
    ]
    for key in ENV_EXAMPLE_REQUIRED_KEYS:
        lines.append(f"{key}={ENV_EXAMPLE_PLACEHOLDERS[key]}")
    lines.extend(["", "# Optional"])
    for key in ENV_EXAMPLE_OPTIONAL_KEYS:
        lines.append(f"{key}={defaults[key]}")
    return "\n".join(lines) + "\n"


def render_live_e2e_example(defaults: dict[str, str]) -> str:
    values = dict(defaults)
    values.update(LIVE_E2E_OVERRIDES)
    lines = [
        "# Live E2E local execution guard",
        "ENABLE_LIVE_E2E=true",
        "",
        "# Required credentials (real test-only credentials)",
        "# Use raw(decoded) key value. Do not pre-URL-encode.",
        f"SERVICE_API_KEY={values['SERVICE_API_KEY']}",
        f"SERVICE_HOOK_URL={values['SERVICE_HOOK_URL']}",
        "",
        "# Required query scope",
        f"AREA_CODES={values['AREA_CODES']}",
        f"AREA_CODE_MAPPING={values['AREA_CODE_MAPPING']}",
        "",
        "# Runtime defaults for safe one-shot validation",
    ]
    runtime_default_keys = [
        "RUN_ONCE",
        "DRY_RUN",
        "LOOKBACK_DAYS",
        "HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS",
        "HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE",
        "CYCLE_INTERVAL_SEC",
        "SHUTDOWN_TIMEOUT_SEC",
        "AREA_INTERVAL_SEC",
        "API_SOFT_RATE_LIMIT_PER_SEC",
        "NOTIFIER_SEND_RATE_LIMIT_PER_SEC",
        "LOG_LEVEL",
        "TIMEZONE",
        "ALERT_RULES_FILE",
    ]
    for key in runtime_default_keys:
        lines.append(f"{key}={values[key]}")

    lines.extend(
        [
            "",
            "# Keep live-e2e state isolated from normal local state",
        ]
    )
    state_file_keys = [
        "SENT_MESSAGES_FILE",
        "HEALTH_STATE_FILE",
        "SQLITE_STATE_FILE",
        "STATE_REPOSITORY_TYPE",
    ]
    for key in state_file_keys:
        lines.append(f"{key}={values[key]}")
    return "\n".join(lines) + "\n"


def _render_setup_defaults_section(defaults: dict[str, str]) -> str:
    lines = [
        SETUP_SECTION_HEADING,
        "",
        "- 생성 기준: `python3 -m scripts.sync_settings_artifacts --write`",
        "",
        SETUP_MARKER_START,
        "| Key | Default (`.env.example`) |",
        "|---|---|",
    ]
    for key in ENV_EXAMPLE_OPTIONAL_KEYS:
        raw_value = defaults[key]
        rendered_value = raw_value if raw_value else "(empty)"
        lines.append(f"| `{key}` | `{rendered_value}` |")
    lines.append(SETUP_MARKER_END)
    lines.append("")
    return "\n".join(lines)


def upsert_setup_defaults_section(*, setup_text: str, defaults: dict[str, str]) -> str:
    section = _render_setup_defaults_section(defaults)
    pattern_with_heading = re.compile(
        rf"{re.escape(SETUP_SECTION_HEADING)}.*?{re.escape(SETUP_MARKER_END)}\n*",
        flags=re.DOTALL,
    )
    if pattern_with_heading.search(setup_text):
        return pattern_with_heading.sub(section + "\n\n", setup_text, count=1)

    pattern_markers_only = re.compile(
        rf"{re.escape(SETUP_MARKER_START)}.*?{re.escape(SETUP_MARKER_END)}\n*",
        flags=re.DOTALL,
    )
    if pattern_markers_only.search(setup_text):
        return pattern_markers_only.sub(section + "\n\n", setup_text, count=1)

    insert_at = setup_text.find(SETUP_INSERT_BEFORE)
    if insert_at < 0:
        return setup_text.rstrip() + "\n\n" + section + "\n"
    return setup_text[:insert_at].rstrip() + "\n\n" + section + "\n\n" + setup_text[insert_at:]


def _render_diff(*, path: Path, expected: str, current: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            expected.splitlines(),
            fromfile=f"{path}:current",
            tofile=f"{path}:expected",
            lineterm="",
        )
    )


def sync_settings_artifacts(*, repo_root: Path, write: bool) -> int:
    defaults = build_settings_env_defaults()
    targets: dict[Path, str] = {
        repo_root / ".env.example": render_env_example(defaults),
        repo_root / ".env.live-e2e.example": render_live_e2e_example(defaults),
    }

    setup_path = repo_root / "docs" / "SETUP.md"
    setup_current = setup_path.read_text(encoding="utf-8")
    targets[setup_path] = upsert_setup_defaults_section(setup_text=setup_current, defaults=defaults)

    mismatches: list[tuple[Path, str, str]] = []
    for path, expected in targets.items():
        current = path.read_text(encoding="utf-8")
        if current != expected:
            mismatches.append((path, expected, current))

    if not mismatches:
        print("settings artifacts are in sync")
        return 0

    if write:
        for path, expected, _ in mismatches:
            path.write_text(expected, encoding="utf-8")
            print(f"updated: {path}")
        return 0

    for path, expected, current in mismatches:
        print(_render_diff(path=path, expected=expected, current=current))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync settings-driven env/doc artifacts (.env*.example, docs/SETUP.md)."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root path.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write expected contents to files. Default is check-only mode.",
    )
    args = parser.parse_args()
    return sync_settings_artifacts(repo_root=args.repo_root, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
