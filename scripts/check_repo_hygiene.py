from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RE_ENV_EXAMPLE_KEY = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=")
RE_SETTINGS_ENV_KEY = re.compile(
    r'(?:os\.getenv|_parse_[a-z_]+_env)\(\s*"([A-Z0-9_]+)"'
)
RE_README_DOC_MAP = re.compile(r"^\s*-\s+`docs/([^`]+\.md)`")

REQUIRED_DOC_FILES = {
    "BACKLOG.md",
    "EVENTS.md",
    "OPERATION.md",
    "SETUP.md",
    "TESTING.md",
}
LEGACY_DOC_FILES = {
    "REFRACTORING_BACKLOG.md",
    "CODEBASE_ASSESSMENT.md",
}


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def parse_env_example_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in _read_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = RE_ENV_EXAMPLE_KEY.match(stripped)
        if match:
            keys.add(match.group(1))
    return keys


def parse_settings_env_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    content = path.read_text(encoding="utf-8")
    return {match.group(1) for match in RE_SETTINGS_ENV_KEY.finditer(content)}


def parse_readme_doc_map(path: Path) -> set[str]:
    docs: set[str] = set()
    for line in _read_lines(path):
        match = RE_README_DOC_MAP.match(line)
        if match:
            docs.add(match.group(1))
    return docs


def build_report(repo_root: Path) -> dict[str, object]:
    docs_dir = repo_root / "docs"
    existing_docs = {path.name for path in docs_dir.glob("*.md")} if docs_dir.exists() else set()

    missing_required_docs = sorted(REQUIRED_DOC_FILES - existing_docs)
    unknown_docs = sorted(existing_docs - REQUIRED_DOC_FILES)
    legacy_docs_present = sorted(name for name in LEGACY_DOC_FILES if (docs_dir / name).exists())

    settings_keys = parse_settings_env_keys(repo_root / "app" / "settings.py")
    env_example_keys = parse_env_example_keys(repo_root / ".env.example")
    missing_in_env_example = sorted(settings_keys - env_example_keys)
    unknown_in_env_example = sorted(env_example_keys - settings_keys)

    readme_doc_map = parse_readme_doc_map(repo_root / "README.md")
    missing_in_readme_doc_map = sorted(REQUIRED_DOC_FILES - readme_doc_map)
    unknown_in_readme_doc_map = sorted(readme_doc_map - REQUIRED_DOC_FILES)

    passed = not (
        missing_required_docs
        or unknown_docs
        or legacy_docs_present
        or missing_in_env_example
        or unknown_in_env_example
        or missing_in_readme_doc_map
        or unknown_in_readme_doc_map
    )
    return {
        "passed": passed,
        "required_docs": sorted(REQUIRED_DOC_FILES),
        "existing_docs": sorted(existing_docs),
        "missing_required_docs": missing_required_docs,
        "unknown_docs": unknown_docs,
        "legacy_docs_present": legacy_docs_present,
        "settings_env_keys_count": len(settings_keys),
        "env_example_keys_count": len(env_example_keys),
        "missing_in_env_example": missing_in_env_example,
        "unknown_in_env_example": unknown_in_env_example,
        "readme_doc_map_count": len(readme_doc_map),
        "missing_in_readme_doc_map": missing_in_readme_doc_map,
        "unknown_in_readme_doc_map": unknown_in_readme_doc_map,
    }


def render_markdown(report: dict[str, object]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Repository Hygiene Check",
        "",
        f"- status: `{status}`",
        f"- required_docs: `{report['required_docs']}`",
        f"- existing_docs: `{report['existing_docs']}`",
        f"- settings_env_keys_count: `{report['settings_env_keys_count']}`",
        f"- env_example_keys_count: `{report['env_example_keys_count']}`",
        f"- readme_doc_map_count: `{report['readme_doc_map_count']}`",
        "",
        f"- missing_required_docs: `{report['missing_required_docs']}`",
        f"- unknown_docs: `{report['unknown_docs']}`",
        f"- legacy_docs_present: `{report['legacy_docs_present']}`",
        f"- missing_in_env_example: `{report['missing_in_env_example']}`",
        f"- unknown_in_env_example: `{report['unknown_in_env_example']}`",
        f"- missing_in_readme_doc_map: `{report['missing_in_readme_doc_map']}`",
        f"- unknown_in_readme_doc_map: `{report['unknown_in_readme_doc_map']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repository hygiene rules.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
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
