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

# shellcheck source=/dev/null
set -a
source "$ENV_FILE"
set +a

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
