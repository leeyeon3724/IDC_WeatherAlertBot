from __future__ import annotations

from app.domain.alert_rules import default_alert_rules

_DEFAULT_RULES = default_alert_rules()

WARN_VAR_MAPPING = dict(_DEFAULT_RULES.code_maps.warn_var)
WARN_STRESS_MAPPING = dict(_DEFAULT_RULES.code_maps.warn_stress)
COMMAND_MAPPING = dict(_DEFAULT_RULES.code_maps.command)
CANCEL_MAPPING = dict(_DEFAULT_RULES.code_maps.cancel)
RESPONSE_CODE_MAPPING = dict(_DEFAULT_RULES.code_maps.response_code)
