from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_HEALTH_STATE_FILE = "./data/api_health_state.json"
MIN_MAX_AGE_SEC = 60
DEFAULT_CYCLE_INTERVAL_SEC = 10


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_utc_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _latest_recorded_at(raw_state: object) -> datetime | None:
    if not isinstance(raw_state, dict):
        return None
    state = raw_state.get("state")
    if not isinstance(state, dict):
        return None
    recent_cycles = state.get("recent_cycles")
    if not isinstance(recent_cycles, list) or not recent_cycles:
        return None

    for item in reversed(recent_cycles):
        if not isinstance(item, dict):
            continue
        recorded_at = _parse_utc_iso(item.get("recorded_at"))
        if recorded_at is not None:
            return recorded_at
    return None


def _resolve_max_age_sec() -> int:
    cycle_interval_raw = os.getenv("CYCLE_INTERVAL_SEC", str(DEFAULT_CYCLE_INTERVAL_SEC)).strip()
    try:
        cycle_interval_sec = int(cycle_interval_raw)
    except ValueError:
        cycle_interval_sec = DEFAULT_CYCLE_INTERVAL_SEC
    cycle_interval_sec = max(cycle_interval_sec, 1)
    return max(MIN_MAX_AGE_SEC, cycle_interval_sec * 12)


def evaluate_health_state(
    *,
    file_path: Path,
    now: datetime,
    max_age_sec: int,
    run_once_mode: bool = False,
) -> tuple[bool, str]:
    if not file_path.exists():
        if run_once_mode:
            return True, f"health-state-run-once-skip:file-missing:{file_path}"
        return False, f"health-state-missing:{file_path}"

    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"health-state-unreadable:{exc}"

    last_recorded_at = _latest_recorded_at(raw)
    if last_recorded_at is None:
        try:
            mtime = file_path.stat().st_mtime
        except OSError as exc:
            return False, f"health-state-stat-failed:{exc}"
        last_recorded_at = datetime.fromtimestamp(mtime, tz=UTC)

    age_sec = max(0.0, (now - last_recorded_at).total_seconds())
    if run_once_mode:
        return True, f"health-state-run-once-skip:age={int(age_sec)}s"
    if age_sec > max_age_sec:
        return False, f"health-state-stale:age={int(age_sec)}s,max={max_age_sec}s"
    return True, f"health-state-ok:age={int(age_sec)}s,max={max_age_sec}s"


def main() -> int:
    health_state_file = Path(
        os.getenv("HEALTH_STATE_FILE", DEFAULT_HEALTH_STATE_FILE).strip()
        or DEFAULT_HEALTH_STATE_FILE
    )
    max_age_sec = _resolve_max_age_sec()
    run_once_mode = _parse_bool_env("RUN_ONCE", default=False)
    ok, reason = evaluate_health_state(
        file_path=health_state_file,
        now=datetime.now(UTC),
        max_age_sec=max_age_sec,
        run_once_mode=run_once_mode,
    )
    print(reason)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
