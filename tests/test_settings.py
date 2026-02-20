from __future__ import annotations

import pytest

from app.settings import Settings, SettingsError


def _clear_known_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "SERVICE_API_KEY",
        "SERVICE_HOOK_URL",
        "WEATHER_ALERT_DATA_API_URL",
        "SENT_MESSAGES_FILE",
        "AREA_CODES",
        "AREA_CODE_MAPPING",
        "REQUEST_TIMEOUT_SEC",
        "REQUEST_CONNECT_TIMEOUT_SEC",
        "REQUEST_READ_TIMEOUT_SEC",
        "MAX_RETRIES",
        "RETRY_DELAY_SEC",
        "NOTIFIER_TIMEOUT_SEC",
        "NOTIFIER_CONNECT_TIMEOUT_SEC",
        "NOTIFIER_READ_TIMEOUT_SEC",
        "NOTIFIER_MAX_RETRIES",
        "NOTIFIER_RETRY_DELAY_SEC",
        "AREA_MAX_WORKERS",
        "LOOKBACK_DAYS",
        "CYCLE_INTERVAL_SEC",
        "AREA_INTERVAL_SEC",
        "CLEANUP_ENABLED",
        "CLEANUP_RETENTION_DAYS",
        "CLEANUP_INCLUDE_UNSENT",
        "BOT_NAME",
        "TIMEZONE",
        "LOG_LEVEL",
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
        "HEALTH_STATE_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_settings_from_env_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    settings = Settings.from_env(env_file=None)

    assert settings.service_api_key == "key-123"
    assert settings.service_hook_url == "https://hook.example"
    assert settings.area_codes == ["11B00000"]
    assert settings.area_code_mapping["11B00000"] == "서울"
    assert settings.sent_messages_file.as_posix().endswith("data/sent_messages.json")
    assert settings.notifier_max_retries == 3
    assert settings.notifier_retry_delay_sec == 1
    assert settings.request_connect_timeout_sec == 5
    assert settings.request_read_timeout_sec == 5
    assert settings.notifier_timeout_sec == 5
    assert settings.notifier_connect_timeout_sec == 5
    assert settings.notifier_read_timeout_sec == 5
    assert settings.area_max_workers == 1
    assert settings.lookback_days == 0
    assert settings.cleanup_enabled is True
    assert settings.cleanup_retention_days == 30
    assert settings.cleanup_include_unsent is True
    assert settings.health_alert_enabled is True
    assert settings.health_outage_window_sec == 600
    assert settings.health_outage_fail_ratio_threshold == 0.7
    assert settings.health_outage_min_failed_cycles == 6
    assert settings.health_outage_consecutive_failures == 4
    assert settings.health_recovery_window_sec == 900
    assert settings.health_recovery_max_fail_ratio == 0.1
    assert settings.health_recovery_consecutive_successes == 8
    assert settings.health_heartbeat_interval_sec == 3600
    assert settings.health_backoff_max_sec == 900
    assert settings.health_recovery_backfill_max_days == 3
    assert settings.health_state_file.as_posix().endswith("data/api_health_state.json")


def test_settings_bool_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("RUN_ONCE", "1")

    settings = Settings.from_env(env_file=None)

    assert settings.dry_run is True
    assert settings.run_once is True


def test_settings_invalid_area_codes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", "not-a-json")
    monkeypatch.setenv("AREA_CODE_MAPPING", "{}")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_invalid_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("DRY_RUN", "maybe")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_loads_from_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_known_env(monkeypatch)
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "\n".join(
            [
                "SERVICE_API_KEY=dotenv-key",
                "SERVICE_HOOK_URL=https://hook.from.dotenv",
                'AREA_CODES=["11B00000"]',
                'AREA_CODE_MAPPING={"11B00000":"서울"}',
                "DRY_RUN=true",
                "RUN_ONCE=true",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings.from_env(env_file=env_file)
    assert settings.service_api_key == "dotenv-key"
    assert settings.service_hook_url == "https://hook.from.dotenv"
    assert settings.dry_run is True
    assert settings.run_once is True


def test_settings_env_precedence_over_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_known_env(monkeypatch)
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "\n".join(
            [
                "SERVICE_API_KEY=dotenv-key",
                "SERVICE_HOOK_URL=https://hook.from.dotenv",
                'AREA_CODES=["11B00000"]',
                'AREA_CODE_MAPPING={"11B00000":"서울"}',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SERVICE_API_KEY", "env-key")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.from.env")

    settings = Settings.from_env(env_file=env_file)
    assert settings.service_api_key == "env-key"
    assert settings.service_hook_url == "https://hook.from.env"


def test_settings_timeout_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("REQUEST_TIMEOUT_SEC", "7")
    monkeypatch.setenv("REQUEST_CONNECT_TIMEOUT_SEC", "2")
    monkeypatch.setenv("REQUEST_READ_TIMEOUT_SEC", "9")
    monkeypatch.setenv("NOTIFIER_TIMEOUT_SEC", "6")
    monkeypatch.setenv("NOTIFIER_CONNECT_TIMEOUT_SEC", "3")
    monkeypatch.setenv("NOTIFIER_READ_TIMEOUT_SEC", "8")
    monkeypatch.setenv("AREA_MAX_WORKERS", "4")

    settings = Settings.from_env(env_file=None)
    assert settings.request_timeout_sec == 7
    assert settings.request_connect_timeout_sec == 2
    assert settings.request_read_timeout_sec == 9
    assert settings.notifier_timeout_sec == 6
    assert settings.notifier_connect_timeout_sec == 3
    assert settings.notifier_read_timeout_sec == 8
    assert settings.area_max_workers == 4


def test_settings_invalid_health_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("HEALTH_OUTAGE_FAIL_RATIO_THRESHOLD", "1.5")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)
