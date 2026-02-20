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
        "MAX_RETRIES",
        "RETRY_DELAY_SEC",
        "NOTIFIER_MAX_RETRIES",
        "NOTIFIER_RETRY_DELAY_SEC",
        "CYCLE_INTERVAL_SEC",
        "AREA_INTERVAL_SEC",
        "BOT_NAME",
        "TIMEZONE",
        "LOG_LEVEL",
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
