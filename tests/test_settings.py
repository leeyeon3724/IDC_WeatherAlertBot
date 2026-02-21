from __future__ import annotations

import json

import pytest

from app.domain.alert_rules import DEFAULT_ALERT_RULES_FILE
from app.settings import Settings, SettingsError


def _clear_known_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "SERVICE_API_KEY",
        "SERVICE_HOOK_URL",
        "WEATHER_ALERT_DATA_API_URL",
        "WEATHER_API_WARNING_TYPE",
        "WEATHER_API_STATION_ID",
        "WEATHER_API_ALLOWED_HOSTS",
        "WEATHER_API_ALLOWED_PATH_PREFIXES",
        "ALERT_RULES_FILE",
        "SENT_MESSAGES_FILE",
        "STATE_REPOSITORY_TYPE",
        "SQLITE_STATE_FILE",
        "AREA_CODES",
        "AREA_CODE_MAPPING",
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
        "HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS",
        "HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE",
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
    assert settings.weather_api_warning_type is None
    assert settings.weather_api_station_id is None
    assert settings.sent_messages_file.as_posix().endswith("data/sent_messages.json")
    assert settings.state_repository_type == "sqlite"
    assert settings.sqlite_state_file.as_posix().endswith("data/sent_messages.db")
    assert settings.notifier_max_retries == 3
    assert settings.notifier_retry_delay_sec == 1
    assert settings.notifier_send_rate_limit_per_sec == 1.0
    assert settings.notifier_max_attempts_per_cycle == 100
    assert settings.notifier_circuit_breaker_enabled is True
    assert settings.notifier_circuit_failure_threshold == 5
    assert settings.notifier_circuit_reset_sec == 300
    assert settings.api_soft_rate_limit_per_sec == 30
    assert settings.request_connect_timeout_sec == 5
    assert settings.request_read_timeout_sec == 5
    assert settings.notifier_timeout_sec == 5
    assert settings.notifier_connect_timeout_sec == 5
    assert settings.notifier_read_timeout_sec == 5
    assert settings.area_max_workers == 1
    assert settings.lookback_days == 0
    assert settings.cleanup_enabled is True
    assert settings.cleanup_retention_days == 30
    assert settings.cleanup_include_unsent is False
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
    assert settings.health_recovery_backfill_window_days == 1
    assert settings.health_recovery_backfill_max_windows_per_cycle == 3
    assert settings.health_state_file.as_posix().endswith("data/api_health_state.json")


def test_settings_loads_alert_rules_from_custom_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    rules_payload = json.loads(DEFAULT_ALERT_RULES_FILE.read_text(encoding="utf-8"))
    rules_payload["unmapped_code_policy"] = "fail"
    rules_payload["message_rules"]["publish_template"] = (
        "[커스텀] {time} {area_name} {warn_var}{warn_stress}"
    )
    rules_file = tmp_path / "alert_rules.custom.json"
    rules_file.write_text(
        json.dumps(rules_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setenv("ALERT_RULES_FILE", str(rules_file))

    settings = Settings.from_env(env_file=None)

    assert settings.alert_rules.unmapped_code_policy == "fail"
    assert settings.alert_rules.message_rules.publish_template.startswith("[커스텀]")


def test_settings_accepts_alert_rules_v2_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("ALERT_RULES_FILE", "./config/alert_rules.v2.json")

    settings = Settings.from_env(env_file=None)

    assert settings.alert_rules.schema_version == 2
    assert settings.alert_rules.code_maps.warn_var["2"] == "호우"


def test_settings_rejects_invalid_alert_rules_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    rules_payload = json.loads(DEFAULT_ALERT_RULES_FILE.read_text(encoding="utf-8"))
    rules_payload["message_rules"]["publish_template"] = "{time}"
    rules_file = tmp_path / "alert_rules.invalid.json"
    rules_file.write_text(
        json.dumps(rules_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setenv("ALERT_RULES_FILE", str(rules_file))

    with pytest.raises(SettingsError, match="ALERT_RULES_FILE"):
        Settings.from_env(env_file=None)


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


def test_settings_accepts_optional_weather_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("WEATHER_API_WARNING_TYPE", "6")
    monkeypatch.setenv("WEATHER_API_STATION_ID", "108")

    settings = Settings.from_env(env_file=None)

    assert settings.weather_api_warning_type == "6"
    assert settings.weather_api_station_id == "108"


def test_settings_rejects_non_digit_optional_weather_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("WEATHER_API_WARNING_TYPE", "rain")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_url_encoded_service_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "abc%2Bdef%3D")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    with pytest.raises(SettingsError, match="URL-encoded"):
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
    monkeypatch.setenv("NOTIFIER_MAX_ATTEMPTS_PER_CYCLE", "50")
    monkeypatch.setenv("NOTIFIER_SEND_RATE_LIMIT_PER_SEC", "0.5")
    monkeypatch.setenv("NOTIFIER_CIRCUIT_BREAKER_ENABLED", "false")
    monkeypatch.setenv("NOTIFIER_CIRCUIT_FAILURE_THRESHOLD", "7")
    monkeypatch.setenv("NOTIFIER_CIRCUIT_RESET_SEC", "120")
    monkeypatch.setenv("API_SOFT_RATE_LIMIT_PER_SEC", "12")
    monkeypatch.setenv("AREA_MAX_WORKERS", "4")

    settings = Settings.from_env(env_file=None)
    assert settings.request_timeout_sec == 7
    assert settings.request_connect_timeout_sec == 2
    assert settings.request_read_timeout_sec == 9
    assert settings.notifier_timeout_sec == 6
    assert settings.notifier_connect_timeout_sec == 3
    assert settings.notifier_read_timeout_sec == 8
    assert settings.notifier_send_rate_limit_per_sec == 0.5
    assert settings.notifier_max_attempts_per_cycle == 50
    assert settings.notifier_circuit_breaker_enabled is False
    assert settings.notifier_circuit_failure_threshold == 7
    assert settings.notifier_circuit_reset_sec == 120
    assert settings.api_soft_rate_limit_per_sec == 12
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


def test_settings_invalid_repository_type(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("STATE_REPOSITORY_TYPE", "postgres")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_non_https_hook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "http://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_non_http_weather_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv(
        "WEATHER_ALERT_DATA_API_URL",
        "https://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd",
    )

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_disallowed_weather_api_host(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv(
        "WEATHER_ALERT_DATA_API_URL",
        "http://evil.example/1360000/WthrWrnInfoService/getPwnCd",
    )

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_disallowed_weather_api_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("WEATHER_API_ALLOWED_HOSTS", '["apis.data.go.kr"]')
    monkeypatch.setenv(
        "WEATHER_ALERT_DATA_API_URL",
        "http://apis.data.go.kr/another-service/path",
    )

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_accepts_custom_allowed_weather_api_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("WEATHER_API_ALLOWED_HOSTS", '["api.internal.local"]')
    monkeypatch.setenv("WEATHER_API_ALLOWED_PATH_PREFIXES", '["/proxy/weather/"]')
    monkeypatch.setenv(
        "WEATHER_ALERT_DATA_API_URL",
        "http://api.internal.local/proxy/weather/getPwnCd",
    )

    settings = Settings.from_env(env_file=None)
    assert settings.weather_alert_data_api_url == "http://api.internal.local/proxy/weather/getPwnCd"


def test_settings_rejects_empty_weather_api_allowed_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("WEATHER_API_ALLOWED_HOSTS", "[]")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_empty_weather_api_allowed_path_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("WEATHER_API_ALLOWED_PATH_PREFIXES", "[]")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_negative_cleanup_retention_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("CLEANUP_RETENTION_DAYS", "-1")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_invalid_notifier_circuit_failure_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("NOTIFIER_CIRCUIT_FAILURE_THRESHOLD", "0")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_negative_api_soft_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("API_SOFT_RATE_LIMIT_PER_SEC", "-1")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_rejects_negative_notifier_send_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("NOTIFIER_SEND_RATE_LIMIT_PER_SEC", "-0.1")

    with pytest.raises(SettingsError):
        Settings.from_env(env_file=None)


def test_settings_allows_incomplete_area_code_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AREA_CODE_MAPPING 누락이 있어도 기동 가능해야 한다(런타임 fallback)."""
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000", "11C00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')  # 11C00000 누락

    settings = Settings.from_env(env_file=None)
    assert settings.area_codes == ["11B00000", "11C00000"]
    assert settings.area_code_mapping["11B00000"] == "서울"
    assert "11C00000" not in settings.area_code_mapping


def test_settings_allows_empty_area_code_mapping_when_codes_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AREA_CODE_MAPPING이 비어 있어도 런타임 fallback을 위해 허용한다."""
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", "{}")

    settings = Settings.from_env(env_file=None)
    assert settings.area_codes == ["11B00000"]
    assert settings.area_code_mapping == {}


def test_settings_rejects_invalid_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    """잘못된 TIMEZONE 값은 Settings.from_env() 시점에 SettingsError를 발생시켜야 한다."""
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("TIMEZONE", "Invalid/Zone")

    with pytest.raises(SettingsError, match="TIMEZONE"):
        Settings.from_env(env_file=None)


def test_settings_accepts_valid_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    """유효한 TIMEZONE 값은 SettingsError 없이 로드되어야 한다."""
    _clear_known_env(monkeypatch)
    monkeypatch.setenv("SERVICE_API_KEY", "key-123")
    monkeypatch.setenv("SERVICE_HOOK_URL", "https://hook.example")
    monkeypatch.setenv("AREA_CODES", '["11B00000"]')
    monkeypatch.setenv("AREA_CODE_MAPPING", '{"11B00000":"서울"}')
    monkeypatch.setenv("TIMEZONE", "America/New_York")

    settings = Settings.from_env(env_file=None)
    assert settings.timezone == "America/New_York"
