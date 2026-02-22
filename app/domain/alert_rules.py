from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

ALERT_RULES_SCHEMA_VERSION = 1
ALLOWED_UNMAPPED_CODE_POLICIES = {"fallback", "fail"}
DEFAULT_ALERT_RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "alert_rules.v1.json"


class AlertRulesError(ValueError):
    """Raised when alert code/message rules are missing or malformed."""


@dataclass(frozen=True)
class AlertCodeMaps:
    warn_var: dict[str, str]
    warn_stress: dict[str, str]
    command: dict[str, str]
    cancel: dict[str, str]
    response_code: dict[str, str]


@dataclass(frozen=True)
class AlertMessageRules:
    normal_cancel_value: str
    publish_command_value: str
    publish_template: str
    release_or_update_template: str
    cancelled_template: str


@dataclass(frozen=True)
class AlertRules:
    schema_version: int
    code_maps: AlertCodeMaps
    message_rules: AlertMessageRules
    unmapped_code_policy: str = "fallback"


AlertRulesLoader = Callable[[dict[str, Any]], AlertRules]
ALERT_RULES_LOADER_REGISTRY: dict[int, AlertRulesLoader] = {}


def register_alert_rules_loader(
    schema_version: int,
) -> Callable[[AlertRulesLoader], AlertRulesLoader]:
    def _decorator(loader: AlertRulesLoader) -> AlertRulesLoader:
        ALERT_RULES_LOADER_REGISTRY[schema_version] = loader
        return loader

    return _decorator


def _clone_mapping(mapping: dict[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in mapping.items()}


def _default_code_maps() -> AlertCodeMaps:
    return AlertCodeMaps(
        warn_var={
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
        },
        warn_stress={
            "0": "주의보",
            "1": "경보",
        },
        command={
            "1": "발표",
            "2": "해제",
            "3": "연장",
            "6": "정정",
            "7": "변경발표",
            "8": "변경해제",
        },
        cancel={
            "0": "정상",
            "1": "취소된 특보",
        },
        response_code={
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
        },
    )


def _default_message_rules() -> AlertMessageRules:
    return AlertMessageRules(
        normal_cancel_value="정상",
        publish_command_value="발표",
        publish_template="{time} {area_name} {warn_var}{warn_stress}가 발표되었습니다.",
        release_or_update_template=(
            "{time} {area_name} {warn_var}{warn_stress}가 {command}되었습니다."
        ),
        cancelled_template=(
            "{time} {command}되었던 {area_name} {warn_var}{warn_stress}가 취소되었습니다."
        ),
    )


def default_alert_rules() -> AlertRules:
    code_maps = _default_code_maps()
    message_rules = _default_message_rules()
    return AlertRules(
        schema_version=ALERT_RULES_SCHEMA_VERSION,
        code_maps=AlertCodeMaps(
            warn_var=_clone_mapping(code_maps.warn_var),
            warn_stress=_clone_mapping(code_maps.warn_stress),
            command=_clone_mapping(code_maps.command),
            cancel=_clone_mapping(code_maps.cancel),
            response_code=_clone_mapping(code_maps.response_code),
        ),
        message_rules=AlertMessageRules(
            normal_cancel_value=message_rules.normal_cancel_value,
            publish_command_value=message_rules.publish_command_value,
            publish_template=message_rules.publish_template,
            release_or_update_template=message_rules.release_or_update_template,
            cancelled_template=message_rules.cancelled_template,
        ),
        unmapped_code_policy="fallback",
    )


def _qualified_key(context: str, key: str) -> str:
    return f"{context}.{key}" if context else key


def _expect_dict(source: dict[str, Any], key: str, *, context: str = "") -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise AlertRulesError(f"{_qualified_key(context, key)} must be a JSON object.")
    return value


def _expect_string(source: dict[str, Any], key: str, *, context: str = "") -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AlertRulesError(f"{_qualified_key(context, key)} must be a non-empty string.")
    return value.strip()


def _expect_string_map(source: dict[str, Any], key: str, *, context: str = "") -> dict[str, str]:
    qualified = _qualified_key(context, key)
    value = _expect_dict(source, key, context=context)
    parsed = {str(k).strip(): str(v).strip() for k, v in value.items()}
    if not parsed:
        raise AlertRulesError(f"{qualified} must include at least one mapping.")
    if any(not item_key for item_key in parsed):
        raise AlertRulesError(f"{qualified} contains an empty mapping key.")
    if any(not item_value for item_value in parsed.values()):
        raise AlertRulesError(f"{qualified} contains an empty mapping value.")
    return parsed


def _validate_template(template: str, *, key: str, allowed: set[str], required: set[str]) -> None:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name is None:
            continue
        name = field_name.strip()
        if not name:
            continue
        if name not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise AlertRulesError(
                f"message_rules.{key} contains unsupported placeholder '{name}'. "
                f"Allowed: {allowed_text}"
            )
        fields.add(name)

    missing = sorted(required - fields)
    if missing:
        raise AlertRulesError(
            f"message_rules.{key} is missing required placeholders: {', '.join(missing)}"
        )


def _parse_code_maps_v1(source: dict[str, Any]) -> AlertCodeMaps:
    return AlertCodeMaps(
        warn_var=_expect_string_map(source, "warn_var", context="code_maps"),
        warn_stress=_expect_string_map(source, "warn_stress", context="code_maps"),
        command=_expect_string_map(source, "command", context="code_maps"),
        cancel=_expect_string_map(source, "cancel", context="code_maps"),
        response_code=_expect_string_map(source, "response_code", context="code_maps"),
    )


def _parse_code_maps_v2(source: dict[str, Any]) -> AlertCodeMaps:
    return AlertCodeMaps(
        warn_var=_expect_string_map(source, "warning_kind", context="mappings"),
        warn_stress=_expect_string_map(source, "warning_level", context="mappings"),
        command=_expect_string_map(source, "announcement_action", context="mappings"),
        cancel=_expect_string_map(source, "cancel_status", context="mappings"),
        response_code=_expect_string_map(source, "api_result", context="mappings"),
    )


def _build_message_rules(
    *,
    normal_cancel_value: str,
    publish_command_value: str,
    publish_template: str,
    release_or_update_template: str,
    cancelled_template: str,
) -> AlertMessageRules:
    rules = AlertMessageRules(
        normal_cancel_value=normal_cancel_value,
        publish_command_value=publish_command_value,
        publish_template=publish_template,
        release_or_update_template=release_or_update_template,
        cancelled_template=cancelled_template,
    )

    shared_placeholders = {"time", "area_name", "warn_var", "warn_stress", "command"}
    _validate_template(
        rules.publish_template,
        key="publish_template",
        allowed=shared_placeholders,
        required={"time", "area_name", "warn_var", "warn_stress"},
    )
    _validate_template(
        rules.release_or_update_template,
        key="release_or_update_template",
        allowed=shared_placeholders,
        required={"time", "area_name", "warn_var", "warn_stress", "command"},
    )
    _validate_template(
        rules.cancelled_template,
        key="cancelled_template",
        allowed=shared_placeholders,
        required={"time", "area_name", "warn_var", "warn_stress", "command"},
    )
    return rules


def _parse_message_rules_v1(source: dict[str, Any]) -> AlertMessageRules:
    return _build_message_rules(
        normal_cancel_value=_expect_string(source, "normal_cancel_value", context="message_rules"),
        publish_command_value=_expect_string(
            source,
            "publish_command_value",
            context="message_rules",
        ),
        publish_template=_expect_string(source, "publish_template", context="message_rules"),
        release_or_update_template=_expect_string(
            source,
            "release_or_update_template",
            context="message_rules",
        ),
        cancelled_template=_expect_string(source, "cancelled_template", context="message_rules"),
    )


def _parse_message_rules_v2(source: dict[str, Any]) -> AlertMessageRules:
    templates = _expect_dict(source, "templates", context="messages")
    return _build_message_rules(
        normal_cancel_value=_expect_string(source, "normal_cancel_value", context="messages"),
        publish_command_value=_expect_string(
            source,
            "publish_command_value",
            context="messages",
        ),
        publish_template=_expect_string(templates, "publish", context="messages.templates"),
        release_or_update_template=_expect_string(
            templates,
            "release_or_update",
            context="messages.templates",
        ),
        cancelled_template=_expect_string(
            templates,
            "cancelled",
            context="messages.templates",
        ),
    )


def _parse_unmapped_code_policy(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_UNMAPPED_CODE_POLICIES:
        allowed_text = ", ".join(sorted(ALLOWED_UNMAPPED_CODE_POLICIES))
        raise AlertRulesError(
            "unmapped_code_policy must be one of: "
            f"{allowed_text}. Received: {normalized}"
        )
    return normalized


def _supported_schema_versions() -> tuple[int, ...]:
    return tuple(sorted(ALERT_RULES_LOADER_REGISTRY))


def _supported_schema_versions_text() -> str:
    return ", ".join(str(version) for version in _supported_schema_versions())


@register_alert_rules_loader(1)
def _load_v1_alert_rules(raw: dict[str, Any]) -> AlertRules:
    code_maps_raw = _expect_dict(raw, "code_maps")
    message_rules_raw = _expect_dict(raw, "message_rules")
    unmapped_code_policy = _parse_unmapped_code_policy(_expect_string(raw, "unmapped_code_policy"))
    return AlertRules(
        schema_version=1,
        code_maps=_parse_code_maps_v1(code_maps_raw),
        message_rules=_parse_message_rules_v1(message_rules_raw),
        unmapped_code_policy=unmapped_code_policy,
    )


@register_alert_rules_loader(2)
def _load_v2_alert_rules(raw: dict[str, Any]) -> AlertRules:
    behavior_raw = _expect_dict(raw, "behavior")
    mappings_raw = _expect_dict(raw, "mappings")
    messages_raw = _expect_dict(raw, "messages")
    unmapped_code_policy = _parse_unmapped_code_policy(
        _expect_string(behavior_raw, "unmapped_code_policy", context="behavior")
    )
    return AlertRules(
        schema_version=2,
        code_maps=_parse_code_maps_v2(mappings_raw),
        message_rules=_parse_message_rules_v2(messages_raw),
        unmapped_code_policy=unmapped_code_policy,
    )


def load_alert_rules(file_path: Path) -> AlertRules:
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AlertRulesError(f"alert rules file not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise AlertRulesError(
            f"alert rules file must be valid JSON: {file_path}"
        ) from exc

    if not isinstance(raw, dict):
        raise AlertRulesError("alert rules root must be a JSON object.")

    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, int):
        raise AlertRulesError("schema_version must be an integer.")
    loader = ALERT_RULES_LOADER_REGISTRY.get(schema_version)
    if loader is None:
        raise AlertRulesError(
            "unsupported schema_version: "
            f"{schema_version} (supported: {_supported_schema_versions_text()})"
        )

    return loader(raw)
