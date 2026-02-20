from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_ALERT_API_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd"
DEFAULT_SENT_MESSAGES_FILE = "./data/sent_messages.json"

WARN_VAR_MAPPING = {
    "1": "강풍",
    "2": "호우",
    "3": "한파",
    "4": "건조",
    "5": "폭풍해일",
    "6": "풍랑",
    "7": "태풍",
    "8": "대설",
    "9": "황사",
    "12": "폭염",
}

WARN_STRESS_MAPPING = {
    "0": "주의보",
    "1": "경보",
}

COMMAND_MAPPING = {
    "1": "발표",
    "2": "해제",
    "3": "연장",
    "6": "정정",
    "7": "변경발표",
    "8": "변경해제",
}

CANCEL_MAPPING = {
    "0": "정상",
    "1": "취소된 특보",
}

RESPONSE_CODE_MAPPING = {
    "00": "정상 (NORMAL_CODE)",
    "01": "어플리케이션 에러 (APPLICATION_ERROR)",
    "02": "데이터베이스 에러 (DB_ERROR)",
    "03": "데이터없음 에러 (NODATA_ERROR)",
    "04": "HTTP 에러 (HTTP_ERROR)",
    "05": "서비스 연결실패 에러 (SERVICETIMEOUT_ERROR)",
    "10": "잘못된 요청 파라메터 에러 (INVALID_REQUEST_PARAMETER_ERROR)",
    "11": "필수 요청 파라메터가 없음 (NO_MANDATORY_REQUEST_PARAMETERS_ERROR)",
    "12": "해당 오픈API서비스가 없거나 폐기됨 (NO_OPENAPI_SERVICE_ERROR)",
    "20": "서비스 접근거부 (SERVICE_ACCESS_DENIED_ERROR)",
    "21": "일시적으로 사용할 수 없는 서비스 키 (TEMPORARILY_DISABLE_THE_SERVICEKEY_ERROR)",
    "22": "서비스 요청제한횟수 초과 (LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR)",
    "30": "등록되지 않은 서비스키 (SERVICE_KEY_IS_NOT_REGISTERED_ERROR)",
    "31": "기한만료된 서비스키 (DEADLINE_HAS_EXPIRED_ERROR)",
    "32": "등록되지 않은 IP (UNREGISTERED_IP_ERROR)",
    "33": "서명되지 않은 호출 (UNSIGNED_CALL_ERROR)",
    "99": "기타에러 (UNKNOWN_ERROR)",
}


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


@dataclass(frozen=True)
class Settings:
    service_api_key: str
    service_hook_url: str
    weather_alert_data_api_url: str
    sent_messages_file: Path
    area_codes: list[str]
    area_code_mapping: dict[str, str]
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

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> "Settings":
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
        )
