from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_ALERT_API_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd"
DEFAULT_SENT_MESSAGES_FILE = "./data/sent_messages.json"
DEFAULT_WEATHER_API_ALLOWED_HOSTS = ["apis.data.go.kr"]
DEFAULT_WEATHER_API_ALLOWED_PATH_PREFIXES = ["/1360000/WthrWrnInfoService/"]


class SettingsError(ValueError):
    """Raised when required environment settings are missing or malformed."""


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv_if_exists(env_file: Path) -> None:
    if not env_file.exists() or not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _strip_optional_quotes(value.strip())
        os.environ.setdefault(key, value)


def _parse_json_env(name: str, default: str, expected_type: type) -> Any:
    raw = os.getenv(name, default)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SettingsError(f"{name} must be valid JSON. Received: {raw}") from exc
    if not isinstance(value, expected_type):
        raise SettingsError(f"{name} must be a JSON {expected_type.__name__}.")
    return value


def _parse_int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be an integer. Received: {raw}") from exc
    if value < minimum:
        raise SettingsError(f"{name} must be >= {minimum}. Received: {value}")
    return value


def _parse_float_env(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a float. Received: {raw}") from exc
    if minimum is not None and value < minimum:
        raise SettingsError(f"{name} must be >= {minimum}. Received: {value}")
    if maximum is not None and value > maximum:
        raise SettingsError(f"{name} must be <= {maximum}. Received: {value}")
    return value


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise SettingsError(
        f"{name} must be a boolean value "
        f"(true/false, 1/0, yes/no). Received: {raw}"
    )


def _parse_choice_env(name: str, default: str, allowed: set[str]) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise SettingsError(f"{name} must be one of: {allowed_text}. Received: {raw}")
    return value


def _parse_non_empty_json_list_env(name: str, default: list[str]) -> list[str]:
    raw_default = json.dumps(default, ensure_ascii=False)
    raw_list = _parse_json_env(name, raw_default, list)
    values = [str(item).strip() for item in raw_list if str(item).strip()]
    if not values:
        raise SettingsError(f"{name} must include at least one non-empty value.")
    return values


def _validate_service_hook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SettingsError(
            "SERVICE_HOOK_URL must be a valid https URL with host."
        )


def _validate_weather_api_url(
    *,
    url: str,
    allowed_hosts: list[str],
    allowed_path_prefixes: list[str],
) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or not parsed.netloc:
        raise SettingsError(
            "WEATHER_ALERT_DATA_API_URL must be a valid http URL with host."
        )

    hostname = (parsed.hostname or "").lower().strip()
    normalized_hosts = {host.lower().strip() for host in allowed_hosts if host.strip()}
    if hostname not in normalized_hosts:
        allowed_text = ", ".join(sorted(normalized_hosts))
        raise SettingsError(
            "WEATHER_ALERT_DATA_API_URL host is not allowed. "
            f"Allowed hosts: {allowed_text}. Received: {hostname}"
        )

    path = parsed.path or "/"
    if not any(path.startswith(prefix) for prefix in allowed_path_prefixes):
        allowed_prefixes = ", ".join(allowed_path_prefixes)
        raise SettingsError(
            "WEATHER_ALERT_DATA_API_URL path is not allowed. "
            f"Allowed prefixes: {allowed_prefixes}. Received: {path}"
        )


@dataclass(frozen=True)
class Settings:
    service_api_key: str
    service_hook_url: str
    weather_alert_data_api_url: str
    sent_messages_file: Path
    area_codes: list[str]
    area_code_mapping: dict[str, str]
    state_repository_type: str = "json"
    sqlite_state_file: Path = Path("./data/sent_messages.db")
    request_timeout_sec: int = 5
    request_connect_timeout_sec: int = 5
    request_read_timeout_sec: int = 5
    max_retries: int = 3
    retry_delay_sec: int = 5
    notifier_timeout_sec: int = 5
    notifier_connect_timeout_sec: int = 5
    notifier_read_timeout_sec: int = 5
    notifier_max_retries: int = 3
    notifier_retry_delay_sec: int = 1
    area_max_workers: int = 1
    lookback_days: int = 0
    cycle_interval_sec: int = 10
    area_interval_sec: int = 5
    cleanup_enabled: bool = True
    cleanup_retention_days: int = 30
    cleanup_include_unsent: bool = True
    bot_name: str = "기상특보알림"
    timezone: str = "Asia/Seoul"
    log_level: str = "INFO"
    dry_run: bool = False
    run_once: bool = False
    health_alert_enabled: bool = True
    health_outage_window_sec: int = 600
    health_outage_fail_ratio_threshold: float = 0.7
    health_outage_min_failed_cycles: int = 6
    health_outage_consecutive_failures: int = 4
    health_recovery_window_sec: int = 900
    health_recovery_max_fail_ratio: float = 0.1
    health_recovery_consecutive_successes: int = 8
    health_heartbeat_interval_sec: int = 3600
    health_backoff_max_sec: int = 900
    health_recovery_backfill_max_days: int = 3
    health_state_file: Path = Path("./data/api_health_state.json")

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> Settings:
        if env_file:
            _load_dotenv_if_exists(Path(env_file))

        service_api_key = os.getenv("SERVICE_API_KEY", "").strip()
        service_hook_url = os.getenv("SERVICE_HOOK_URL", "").strip()
        weather_alert_data_api_url = os.getenv(
            "WEATHER_ALERT_DATA_API_URL",
            DEFAULT_ALERT_API_URL,
        ).strip()

        if not service_api_key:
            raise SettingsError("SERVICE_API_KEY is required.")
        if not service_hook_url:
            raise SettingsError("SERVICE_HOOK_URL is required.")
        _validate_service_hook_url(service_hook_url)

        weather_api_allowed_hosts = _parse_non_empty_json_list_env(
            "WEATHER_API_ALLOWED_HOSTS",
            DEFAULT_WEATHER_API_ALLOWED_HOSTS,
        )
        weather_api_allowed_path_prefixes = _parse_non_empty_json_list_env(
            "WEATHER_API_ALLOWED_PATH_PREFIXES",
            DEFAULT_WEATHER_API_ALLOWED_PATH_PREFIXES,
        )
        _validate_weather_api_url(
            url=weather_alert_data_api_url,
            allowed_hosts=weather_api_allowed_hosts,
            allowed_path_prefixes=weather_api_allowed_path_prefixes,
        )

        area_codes_raw = _parse_json_env("AREA_CODES", "[]", list)
        area_codes = [str(code).strip() for code in area_codes_raw if str(code).strip()]
        if not area_codes:
            raise SettingsError("AREA_CODES must include at least one area code.")

        area_code_mapping_raw = _parse_json_env("AREA_CODE_MAPPING", "{}", dict)
        area_code_mapping = {str(k): str(v) for k, v in area_code_mapping_raw.items()}

        sent_messages_file = Path(
            os.getenv("SENT_MESSAGES_FILE", DEFAULT_SENT_MESSAGES_FILE).strip()
            or DEFAULT_SENT_MESSAGES_FILE
        )
        state_repository_type = _parse_choice_env(
            "STATE_REPOSITORY_TYPE",
            "json",
            {"json", "sqlite"},
        )
        sqlite_state_file = Path(
            os.getenv("SQLITE_STATE_FILE", "./data/sent_messages.db").strip()
            or "./data/sent_messages.db"
        )

        request_timeout_sec = _parse_int_env("REQUEST_TIMEOUT_SEC", 5, minimum=1)
        request_connect_timeout_sec = _parse_int_env(
            "REQUEST_CONNECT_TIMEOUT_SEC",
            request_timeout_sec,
            minimum=1,
        )
        request_read_timeout_sec = _parse_int_env(
            "REQUEST_READ_TIMEOUT_SEC",
            request_timeout_sec,
            minimum=1,
        )
        notifier_timeout_sec = _parse_int_env(
            "NOTIFIER_TIMEOUT_SEC",
            request_timeout_sec,
            minimum=1,
        )
        notifier_connect_timeout_sec = _parse_int_env(
            "NOTIFIER_CONNECT_TIMEOUT_SEC",
            notifier_timeout_sec,
            minimum=1,
        )
        notifier_read_timeout_sec = _parse_int_env(
            "NOTIFIER_READ_TIMEOUT_SEC",
            notifier_timeout_sec,
            minimum=1,
        )

        return cls(
            service_api_key=service_api_key,
            service_hook_url=service_hook_url,
            weather_alert_data_api_url=weather_alert_data_api_url,
            sent_messages_file=sent_messages_file,
            state_repository_type=state_repository_type,
            sqlite_state_file=sqlite_state_file,
            area_codes=area_codes,
            area_code_mapping=area_code_mapping,
            request_timeout_sec=request_timeout_sec,
            request_connect_timeout_sec=request_connect_timeout_sec,
            request_read_timeout_sec=request_read_timeout_sec,
            max_retries=_parse_int_env("MAX_RETRIES", 3, minimum=1),
            retry_delay_sec=_parse_int_env("RETRY_DELAY_SEC", 5, minimum=0),
            notifier_timeout_sec=notifier_timeout_sec,
            notifier_connect_timeout_sec=notifier_connect_timeout_sec,
            notifier_read_timeout_sec=notifier_read_timeout_sec,
            notifier_max_retries=_parse_int_env("NOTIFIER_MAX_RETRIES", 3, minimum=1),
            notifier_retry_delay_sec=_parse_int_env("NOTIFIER_RETRY_DELAY_SEC", 1, minimum=0),
            area_max_workers=_parse_int_env("AREA_MAX_WORKERS", 1, minimum=1),
            lookback_days=_parse_int_env("LOOKBACK_DAYS", 0, minimum=0),
            cycle_interval_sec=_parse_int_env("CYCLE_INTERVAL_SEC", 10, minimum=0),
            area_interval_sec=_parse_int_env("AREA_INTERVAL_SEC", 5, minimum=0),
            cleanup_enabled=_parse_bool_env("CLEANUP_ENABLED", default=True),
            cleanup_retention_days=_parse_int_env("CLEANUP_RETENTION_DAYS", 30, minimum=0),
            cleanup_include_unsent=_parse_bool_env("CLEANUP_INCLUDE_UNSENT", default=True),
            bot_name=os.getenv("BOT_NAME", "기상특보알림").strip() or "기상특보알림",
            timezone=os.getenv("TIMEZONE", "Asia/Seoul").strip() or "Asia/Seoul",
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            dry_run=_parse_bool_env("DRY_RUN", default=False),
            run_once=_parse_bool_env("RUN_ONCE", default=False),
            health_alert_enabled=_parse_bool_env("HEALTH_ALERT_ENABLED", default=True),
            health_outage_window_sec=_parse_int_env("HEALTH_OUTAGE_WINDOW_SEC", 600, minimum=1),
            health_outage_fail_ratio_threshold=_parse_float_env(
                "HEALTH_OUTAGE_FAIL_RATIO_THRESHOLD",
                0.7,
                minimum=0.0,
                maximum=1.0,
            ),
            health_outage_min_failed_cycles=_parse_int_env(
                "HEALTH_OUTAGE_MIN_FAILED_CYCLES",
                6,
                minimum=1,
            ),
            health_outage_consecutive_failures=_parse_int_env(
                "HEALTH_OUTAGE_CONSECUTIVE_FAILURES",
                4,
                minimum=1,
            ),
            health_recovery_window_sec=_parse_int_env("HEALTH_RECOVERY_WINDOW_SEC", 900, minimum=1),
            health_recovery_max_fail_ratio=_parse_float_env(
                "HEALTH_RECOVERY_MAX_FAIL_RATIO",
                0.1,
                minimum=0.0,
                maximum=1.0,
            ),
            health_recovery_consecutive_successes=_parse_int_env(
                "HEALTH_RECOVERY_CONSECUTIVE_SUCCESSES",
                8,
                minimum=1,
            ),
            health_heartbeat_interval_sec=_parse_int_env(
                "HEALTH_HEARTBEAT_INTERVAL_SEC",
                3600,
                minimum=1,
            ),
            health_backoff_max_sec=_parse_int_env("HEALTH_BACKOFF_MAX_SEC", 900, minimum=1),
            health_recovery_backfill_max_days=_parse_int_env(
                "HEALTH_RECOVERY_BACKFILL_MAX_DAYS",
                3,
                minimum=0,
            ),
            health_state_file=Path(
                os.getenv("HEALTH_STATE_FILE", "./data/api_health_state.json").strip()
                or "./data/api_health_state.json"
            ),
        )
