#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env.live-e2e}"
LOG_FILE="${LIVE_E2E_LOG_FILE:-$ROOT_DIR/artifacts/live-e2e/local/service.log}"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >&2 <<EOF
live-e2e env file not found: $ENV_FILE
Create it from template:
  cp .env.live-e2e.example .env.live-e2e
EOF
  exit 1
fi

strip_optional_quotes() {
  local value="$1"
  if [[ ${#value} -ge 2 ]]; then
    local first="${value:0:1}"
    local last="${value: -1}"
    if [[ "$first" == "$last" && ( "$first" == "'" || "$first" == '"' ) ]]; then
      value="${value:1:${#value}-2}"
    fi
  fi
  printf '%s' "$value"
}

load_env_file() {
  local env_file="$1"
  local raw_line line key value
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    line="$raw_line"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" == export\ * ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    if [[ ! "$key" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
      echo "Invalid env key in $env_file: $key" >&2
      exit 1
    fi
    value="$(strip_optional_quotes "$value")"
    export "$key=$value"
  done < "$env_file"
}

load_env_file "$ENV_FILE"

normalize_bool() {
  echo "${1:-}" | tr '[:upper:]' '[:lower:]'
}

if [[ "$(normalize_bool "${ENABLE_LIVE_E2E:-false}")" != "true" ]]; then
  echo "Refusing to run live-e2e: set ENABLE_LIVE_E2E=true in $ENV_FILE" >&2
  exit 1
fi

required_vars=("SERVICE_API_KEY" "SERVICE_HOOK_URL" "AREA_CODES" "AREA_CODE_MAPPING")
for key in "${required_vars[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "Missing required variable: $key" >&2
    exit 1
  fi
done

if [[ "${SERVICE_API_KEY}" == "YOUR_TEST_SERVICE_KEY" ]]; then
  echo "SERVICE_API_KEY still uses template value." >&2
  exit 1
fi
if [[ "${SERVICE_HOOK_URL}" == "https://hook.dooray.com/services/your/test/path" ]]; then
  echo "SERVICE_HOOK_URL still uses template value." >&2
  exit 1
fi

if [[ ! "${SERVICE_HOOK_URL}" =~ ^https:// ]]; then
  echo "SERVICE_HOOK_URL must be https URL." >&2
  exit 1
fi

python3 - <<'PY'
from __future__ import annotations

import json
import os
import sys

checks = (
    ("AREA_CODES", list),
    ("AREA_CODE_MAPPING", dict),
)
for key, expected in checks:
    raw = os.getenv(key, "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"{key} must be valid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(parsed, expected):
        print(
            f"{key} must be a JSON {expected.__name__}.",
            file=sys.stderr,
        )
        raise SystemExit(1)
PY

export RUN_ONCE=true
export DRY_RUN=false
export LOOKBACK_DAYS="${LOOKBACK_DAYS:-0}"
export CYCLE_INTERVAL_SEC=0
export AREA_INTERVAL_SEC=0
export STATE_REPOSITORY_TYPE="${STATE_REPOSITORY_TYPE:-json}"
export SENT_MESSAGES_FILE="${SENT_MESSAGES_FILE:-$ROOT_DIR/artifacts/live-e2e/local/sent_messages.live-e2e.json}"
export HEALTH_STATE_FILE="${HEALTH_STATE_FILE:-$ROOT_DIR/artifacts/live-e2e/local/api_health_state.live-e2e.json}"

mkdir -p "$(dirname "$SENT_MESSAGES_FILE")"
mkdir -p "$(dirname "$HEALTH_STATE_FILE")"
mkdir -p "$(dirname "$LOG_FILE")"

echo "Running live-e2e local one-shot test (log: $LOG_FILE)"
(
  cd "$ROOT_DIR"
  python3 main.py run 2>&1 | tee "$LOG_FILE"
)
