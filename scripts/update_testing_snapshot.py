from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SNAPSHOT_SECTION_PATTERN = re.compile(
    r"(## 2\) 현재 스냅샷\s*\n\n)(.*?)(\n## 3\) 현재 기준)",
    re.DOTALL,
)


def parse_test_snapshot(output: str) -> tuple[int, str]:
    passed_match = re.search(r"(\d+)\s+passed\b", output)
    if passed_match is None:
        raise ValueError("could not parse passed test count from pytest output")

    coverage_match = re.search(r"Total coverage:\s*([0-9]+(?:\.[0-9]+)?)%", output)
    if coverage_match is None:
        total_line_match = re.search(
            r"^\s*TOTAL\s+\d+\s+\d+\s+\d+\s+\d+\s+([0-9]+)%",
            output,
            re.MULTILINE,
        )
        if total_line_match is None:
            raise ValueError("could not parse total coverage from pytest output")
        coverage_text = f"{total_line_match.group(1)}%"
    else:
        coverage_text = f"{coverage_match.group(1)}%"

    return int(passed_match.group(1)), coverage_text


def _extract_minimum_coverage(snapshot_text: str) -> str:
    minimum_match = re.search(r"- 최소 커버리지 기준: `([^`]+)`", snapshot_text)
    if minimum_match is not None:
        return minimum_match.group(1)
    return "80%"


def update_testing_doc(doc_text: str, *, passed_count: int, coverage_text: str) -> str:
    match = SNAPSHOT_SECTION_PATTERN.search(doc_text)
    if match is None:
        raise ValueError("could not find '## 2) 현재 스냅샷' section in docs/TESTING.md")

    minimum_coverage = _extract_minimum_coverage(match.group(2))
    replacement_body = (
        f"- 테스트 수: `{passed_count}`\n"
        f"- 전체 커버리지: `{coverage_text}`\n"
        f"- 최소 커버리지 기준: `{minimum_coverage}`\n"
    )
    return SNAPSHOT_SECTION_PATTERN.sub(
        rf"\1{replacement_body}\3",
        doc_text,
        count=1,
    )


def run_pytest_with_coverage(*, cov_config: str) -> tuple[int, str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov=app",
        "--cov-report=term-missing",
        f"--cov-config={cov_config}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    combined_output = f"{result.stdout}{result.stderr}"
    return result.returncode, combined_output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update docs/TESTING.md snapshot from pytest coverage output."
    )
    parser.add_argument(
        "--doc-file",
        type=Path,
        default=Path("docs/TESTING.md"),
        help="Path to TESTING.md document.",
    )
    parser.add_argument(
        "--cov-config",
        default=".coveragerc",
        help="Coverage config path used for pytest execution.",
    )
    parser.add_argument(
        "--from-log",
        type=Path,
        default=None,
        help="Optional existing pytest log file. If set, pytest is not executed.",
    )
    parser.add_argument(
        "--log-output",
        type=Path,
        default=None,
        help="Optional path to write raw pytest output.",
    )
    args = parser.parse_args()

    if args.from_log is not None:
        raw_output = args.from_log.read_text(encoding="utf-8")
        return_code = 0
    else:
        return_code, raw_output = run_pytest_with_coverage(cov_config=args.cov_config)

    if args.log_output is not None:
        args.log_output.parent.mkdir(parents=True, exist_ok=True)
        args.log_output.write_text(raw_output, encoding="utf-8")

    try:
        passed_count, coverage_text = parse_test_snapshot(raw_output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    doc_text = args.doc_file.read_text(encoding="utf-8")
    updated_doc = update_testing_doc(
        doc_text,
        passed_count=passed_count,
        coverage_text=coverage_text,
    )
    args.doc_file.write_text(updated_doc, encoding="utf-8")

    print(
        f"testing snapshot updated: passed={passed_count}, "
        f"coverage={coverage_text}, doc={args.doc_file}"
    )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
