from __future__ import annotations

import argparse
import json
from pathlib import Path

FULL_GATE_MARKERS = (
    "requirements",
    "pyproject.toml",
    "mypy.ini",
    "pytest.ini",
    ".coveragerc",
    ".github/workflows/ci.yml",
)

PREFIX_TEST_MAP: dict[str, list[str]] = {
    "app/services/weather_api.py": [
        "tests/test_weather_api.py",
        "tests/test_process_cycle.py",
        "tests/test_service_loop.py",
    ],
    "app/services/notifier.py": [
        "tests/test_notifier.py",
        "tests/test_process_cycle.py",
        "tests/test_service_loop.py",
    ],
    "app/entrypoints/": [
        "tests/test_main.py",
        "tests/test_main_smoke.py",
        "tests/test_commands.py",
        "tests/test_service_loop.py",
        "tests/test_contract_snapshots.py",
    ],
    "app/repositories/": [
        "tests/test_json_state_repo.py",
        "tests/test_sqlite_state_repo.py",
        "tests/test_state_migration.py",
        "tests/test_state_models.py",
        "tests/test_health_state_repo.py",
        "tests/test_contract_snapshots.py",
    ],
    "app/settings.py": [
        "tests/test_settings.py",
        "tests/test_main.py",
        "tests/test_contract_snapshots.py",
    ],
    "app/usecases/": [
        "tests/test_process_cycle.py",
        "tests/test_service_loop.py",
        "tests/test_health_monitor.py",
    ],
    "app/domain/": [
        "tests/test_domain.py",
        "tests/test_health_domain.py",
        "tests/test_health_message_builder.py",
    ],
    "scripts/": [
        "tests/test_repo_hygiene.py",
        "tests/test_event_docs_sync.py",
        "tests/test_contract_snapshots.py",
        "tests/test_env_defaults_sync.py",
        "tests/test_update_testing_snapshot.py",
        "tests/test_perf_baseline.py",
        "tests/test_compare_perf_reports.py",
        "tests/test_slo_report.py",
    ],
}

DOCS_ONLY_TESTS = [
    "tests/test_repo_hygiene.py",
    "tests/test_event_docs_sync.py",
    "tests/test_contract_snapshots.py",
]


def _read_changed_files(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _is_docs_only(files: list[str]) -> bool:
    if not files:
        return False
    for file in files:
        if file.startswith("docs/"):
            continue
        if file in {"README.md", ".env.example"}:
            continue
        return False
    return True


def build_report(changed_files: list[str]) -> dict[str, object]:
    selected: set[str] = set()
    reasons: list[str] = []

    if not changed_files:
        return {
            "mode": "fast",
            "selected_tests": DOCS_ONLY_TESTS,
            "reasons": ["no changed files detected; run lightweight contract checks"],
            "changed_files_count": 0,
        }

    for file in changed_files:
        if file.startswith("tests/") and file.endswith(".py"):
            selected.add(file)

    for file in changed_files:
        if any(marker in file for marker in FULL_GATE_MARKERS):
            return {
                "mode": "full",
                "selected_tests": [],
                "reasons": [f"full gate marker changed: {file}"],
                "changed_files_count": len(changed_files),
            }
        for prefix, tests in PREFIX_TEST_MAP.items():
            if file.startswith(prefix):
                selected.update(tests)

    if _is_docs_only(changed_files):
        selected.update(DOCS_ONLY_TESTS)
        reasons.append("docs-only change; run doc/contract checks")

    if not selected:
        return {
            "mode": "full",
            "selected_tests": [],
            "reasons": ["could not map changed files to safe fast-test subset"],
            "changed_files_count": len(changed_files),
        }

    return {
        "mode": "fast",
        "selected_tests": sorted(selected),
        "reasons": reasons or ["selected tests from change-impact mapping"],
        "changed_files_count": len(changed_files),
    }


def render_markdown(report: dict[str, object]) -> str:
    selected_tests = report["selected_tests"]
    lines = [
        "## Selected Tests",
        "",
        f"- mode: `{report['mode']}`",
        f"- changed_files_count: `{report['changed_files_count']}`",
        f"- reasons: `{report['reasons']}`",
        f"- selected_tests_count: `{len(selected_tests)}`",
        "",
        "```",
    ]
    for test in selected_tests:
        lines.append(str(test))
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select pytest targets from changed files.")
    parser.add_argument(
        "--changed-files-file",
        type=Path,
        required=True,
        help="Path to newline-delimited changed files list.",
    )
    parser.add_argument(
        "--selected-output",
        type=Path,
        default=None,
        help="Optional selected tests output file (one per line).",
    )
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    changed_files = _read_changed_files(args.changed_files_file)
    report = build_report(changed_files)
    selected_tests = [str(item) for item in report["selected_tests"]]

    if args.selected_output is not None:
        args.selected_output.parent.mkdir(parents=True, exist_ok=True)
        args.selected_output.write_text("\n".join(selected_tests) + "\n", encoding="utf-8")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
