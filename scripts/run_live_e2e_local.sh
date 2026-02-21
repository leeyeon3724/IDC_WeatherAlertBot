#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env.live-e2e}"
LOG_FILE="${LIVE_E2E_LOG_FILE:-$ROOT_DIR/artifacts/live-e2e/local/service.log}"
ARTIFACT_DIR="${LIVE_E2E_ARTIFACT_DIR:-$(dirname "$LOG_FILE")}"
WEBHOOK_PROBE_FILE="${LIVE_E2E_WEBHOOK_PROBE_FILE:-$ARTIFACT_DIR/webhook_probe.json}"
REPORT_JSON_FILE="${LIVE_E2E_REPORT_JSON_FILE:-$ARTIFACT_DIR/report.json}"
REPORT_MD_FILE="${LIVE_E2E_REPORT_MD_FILE:-$ARTIFACT_DIR/report.md}"
SLO_JSON_FILE="${LIVE_E2E_SLO_JSON_FILE:-$ARTIFACT_DIR/slo_report.json}"
SLO_MD_FILE="${LIVE_E2E_SLO_MD_FILE:-$ARTIFACT_DIR/slo_report.md}"

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
mkdir -p "$ARTIFACT_DIR"

echo "Running live-e2e local one-shot test (log: $LOG_FILE)"
set +e
(
  cd "$ROOT_DIR"
  python3 main.py run 2>&1 | tee "$LOG_FILE"
)
service_exit_code=$?
set -e

echo "Running live-e2e webhook probe (result: $WEBHOOK_PROBE_FILE)"
set +e
WEBHOOK_PROBE_FILE="$WEBHOOK_PROBE_FILE" python3 - <<'PY'
from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from app.services.notifier import DoorayNotifier

output = os.environ["WEBHOOK_PROBE_FILE"]
webhook_url = os.environ["SERVICE_HOOK_URL"]
result = {
    "passed": False,
    "error": "",
    "timestamp_utc": datetime.now(UTC).isoformat(),
}
try:
    notifier = DoorayNotifier(
        hook_url=webhook_url,
        bot_name="weather-alert-live-e2e-local",
        timeout_sec=5,
        connect_timeout_sec=5,
        read_timeout_sec=5,
        max_retries=2,
        retry_delay_sec=1,
    )
    notifier.send(
        "[live-e2e-local] webhook delivery probe "
        + datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    result["passed"] = True
except Exception as exc:
    result["error"] = str(exc)

with open(output, "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2, sort_keys=True)

raise SystemExit(0 if result["passed"] else 1)
PY
webhook_probe_exit_code=$?
set -e

echo "Building local live-e2e canary report"
set +e
(
  cd "$ROOT_DIR"
  python3 -m scripts.canary_report \
    --log-file "$LOG_FILE" \
    --service-exit-code "$service_exit_code" \
    --webhook-probe-file "$WEBHOOK_PROBE_FILE" \
    --json-output "$REPORT_JSON_FILE" \
    --markdown-output "$REPORT_MD_FILE"
)
canary_report_exit_code=$?

echo "Building local live-e2e SLO report"
(
  cd "$ROOT_DIR"
  python3 -m scripts.slo_report \
    --log-file "$LOG_FILE" \
    --min-success-rate 1.0 \
    --max-failure-rate 0.0 \
    --max-p95-cycle-latency-sec 600 \
    --max-pending-latest 0 \
    --json-output "$SLO_JSON_FILE" \
    --markdown-output "$SLO_MD_FILE"
)
slo_report_exit_code=$?
set -e

echo "Local live-e2e artifacts:"
echo "  - log: $LOG_FILE"
echo "  - webhook probe: $WEBHOOK_PROBE_FILE"
echo "  - canary report: $REPORT_JSON_FILE"
echo "  - canary markdown: $REPORT_MD_FILE"
echo "  - slo report: $SLO_JSON_FILE"
echo "  - slo markdown: $SLO_MD_FILE"

if [[ "$canary_report_exit_code" -ne 0 || "$slo_report_exit_code" -ne 0 ]]; then
  echo "live-e2e local verification failed." >&2
  echo "  service_exit_code=$service_exit_code" >&2
  echo "  webhook_probe_exit_code=$webhook_probe_exit_code" >&2
  echo "  canary_report_exit_code=$canary_report_exit_code" >&2
  echo "  slo_report_exit_code=$slo_report_exit_code" >&2
  exit 1
fi

echo "live-e2e local verification passed."
