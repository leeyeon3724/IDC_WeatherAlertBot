from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RE_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")
RE_COMPOSE_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*:\s*(.+?)\s*$")

LIVE_E2E_ALLOWLIST = {
    "SERVICE_API_KEY",
    "SERVICE_HOOK_URL",
    "AREA_CODES",
    "AREA_CODE_MAPPING",
    "RUN_ONCE",
    "DRY_RUN",
    "LOOKBACK_DAYS",
    "CYCLE_INTERVAL_SEC",
    "AREA_INTERVAL_SEC",
    "SENT_MESSAGES_FILE",
    "SQLITE_STATE_FILE",
    "HEALTH_STATE_FILE",
}
DOCKER_COMPOSE_ALLOWLIST = {"AREA_MAX_WORKERS"}


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_env_map(path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if not path.exists():
        return env_map
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        match = RE_ENV_LINE.match(line)
        if match is None:
            continue
        env_map[match.group(1)] = _strip_quotes(match.group(2))
    return env_map


def parse_compose_environment(path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if not path.exists():
        return env_map

    lines = path.read_text(encoding="utf-8").splitlines()
    env_indent: int | None = None
    for raw_line in lines:
        if env_indent is None:
            if raw_line.strip() == "environment:":
                env_indent = len(raw_line) - len(raw_line.lstrip())
            continue

        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = len(raw_line) - len(raw_line.lstrip())
        if line_indent <= env_indent:
            break
        match = RE_COMPOSE_ENV_LINE.match(raw_line)
        if match is None:
            continue
        env_map[match.group(1)] = _strip_quotes(match.group(2))
    return env_map


def _diff_values(
    *,
    left: dict[str, str],
    right: dict[str, str],
    allowlist: set[str],
) -> list[dict[str, str]]:
    diffs: list[dict[str, str]] = []
    for key in sorted((set(left) & set(right)) - allowlist):
        if left[key] == right[key]:
            continue
        diffs.append({"key": key, "left": left[key], "right": right[key]})
    return diffs


def build_report(repo_root: Path) -> dict[str, object]:
    env_example = parse_env_map(repo_root / ".env.example")
    env_live = parse_env_map(repo_root / ".env.live-e2e.example")
    compose_env = parse_compose_environment(repo_root / "docker-compose.yml")

    live_disallowed_diffs = _diff_values(
        left=env_example,
        right=env_live,
        allowlist=LIVE_E2E_ALLOWLIST,
    )
    compose_disallowed_diffs = _diff_values(
        left=env_example,
        right=compose_env,
        allowlist=DOCKER_COMPOSE_ALLOWLIST,
    )
    compose_unknown_keys = sorted(set(compose_env) - set(env_example))

    passed = not (live_disallowed_diffs or compose_disallowed_diffs or compose_unknown_keys)
    return {
        "passed": passed,
        "env_example_keys_count": len(env_example),
        "env_live_e2e_keys_count": len(env_live),
        "docker_compose_env_keys_count": len(compose_env),
        "live_e2e_allowlist": sorted(LIVE_E2E_ALLOWLIST),
        "docker_compose_allowlist": sorted(DOCKER_COMPOSE_ALLOWLIST),
        "live_e2e_disallowed_diffs": live_disallowed_diffs,
        "docker_compose_disallowed_diffs": compose_disallowed_diffs,
        "docker_compose_unknown_keys": compose_unknown_keys,
    }


def render_markdown(report: dict[str, object]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Env Defaults Sync Check",
        "",
        f"- status: `{status}`",
        f"- env_example_keys_count: `{report['env_example_keys_count']}`",
        f"- env_live_e2e_keys_count: `{report['env_live_e2e_keys_count']}`",
        f"- docker_compose_env_keys_count: `{report['docker_compose_env_keys_count']}`",
        f"- live_e2e_allowlist: `{report['live_e2e_allowlist']}`",
        f"- docker_compose_allowlist: `{report['docker_compose_allowlist']}`",
        "",
        f"- live_e2e_disallowed_diffs: `{report['live_e2e_disallowed_diffs']}`",
        f"- docker_compose_disallowed_diffs: `{report['docker_compose_disallowed_diffs']}`",
        f"- docker_compose_unknown_keys: `{report['docker_compose_unknown_keys']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate env defaults consistency.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    report = build_report(args.repo_root)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    markdown = render_markdown(report)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(markdown)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
