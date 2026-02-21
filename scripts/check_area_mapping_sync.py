from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RE_ENV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")


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


def _load_json_value(
    *,
    env_map: dict[str, str],
    key: str,
    expected_type: type,
) -> tuple[object | None, str | None]:
    raw = env_map.get(key)
    if raw is None:
        return None, f"{key}:missing"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"{key}:invalid_json"
    if not isinstance(value, expected_type):
        return None, f"{key}:expected_{expected_type.__name__}"
    return value, None


def evaluate_env_file(path: Path) -> dict[str, object]:
    exists = path.exists()
    if not exists:
        return {
            "file": path.as_posix(),
            "exists": False,
            "errors": ["file:missing"],
            "area_codes_count": 0,
            "mapping_count": 0,
            "missing_mapping_keys": [],
            "coverage_pct": 0.0,
        }

    env_map = parse_env_map(path)
    errors: list[str] = []

    area_codes_obj, area_codes_error = _load_json_value(
        env_map=env_map,
        key="AREA_CODES",
        expected_type=list,
    )
    if area_codes_error is not None:
        errors.append(area_codes_error)
    area_codes = (
        [str(code).strip() for code in area_codes_obj if str(code).strip()]
        if isinstance(area_codes_obj, list)
        else []
    )

    mapping_obj, mapping_error = _load_json_value(
        env_map=env_map,
        key="AREA_CODE_MAPPING",
        expected_type=dict,
    )
    if mapping_error is not None:
        errors.append(mapping_error)
    mapping = (
        {str(key).strip(): str(value).strip() for key, value in mapping_obj.items()}
        if isinstance(mapping_obj, dict)
        else {}
    )

    missing_mapping_keys = sorted(code for code in area_codes if code not in mapping)
    mapped_count = len(area_codes) - len(missing_mapping_keys)
    coverage_pct = round((mapped_count / len(area_codes) * 100.0), 2) if area_codes else 0.0

    return {
        "file": path.as_posix(),
        "exists": True,
        "errors": errors,
        "area_codes_count": len(area_codes),
        "mapping_count": len(mapping),
        "missing_mapping_keys": missing_mapping_keys,
        "coverage_pct": coverage_pct,
    }


def build_report(repo_root: Path) -> dict[str, object]:
    targets = [repo_root / ".env.example", repo_root / ".env.live-e2e.example"]
    file_reports = [evaluate_env_file(path) for path in targets]
    missing_or_invalid = [
        {"file": report["file"], "errors": report["errors"]}
        for report in file_reports
        if not report["exists"] or bool(report["errors"])
    ]
    mapping_gaps = [
        {
            "file": report["file"],
            "missing_mapping_keys": report["missing_mapping_keys"],
        }
        for report in file_reports
        if bool(report["missing_mapping_keys"])
    ]
    passed = not (missing_or_invalid or mapping_gaps)
    return {
        "passed": passed,
        "files": file_reports,
        "missing_or_invalid": missing_or_invalid,
        "mapping_gaps": mapping_gaps,
    }


def render_markdown(report: dict[str, object]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Area Mapping Sync Check",
        "",
        f"- status: `{status}`",
        f"- files: `{report['files']}`",
        "",
        f"- missing_or_invalid: `{report['missing_or_invalid']}`",
        f"- mapping_gaps: `{report['mapping_gaps']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AREA_CODES and AREA_CODE_MAPPING sync.")
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
