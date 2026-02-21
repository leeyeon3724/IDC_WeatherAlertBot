from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.event_payload_contract import build_event_payload_contract

RE_TIMESTAMP = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
RE_EVENT_TOKEN = re.compile(r"`([^`]+)`")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("`", "").strip())


def _event_key(event: str, variant: str | None) -> str:
    return f"{event}#{variant or ''}"


def _parse_markdown_table_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    in_alarm_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("| 신호(Event) |"):
            in_alarm_table = True
            continue
        if not in_alarm_table:
            continue
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        if stripped.startswith("|---"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue

        signal = cells[0]
        threshold = cells[1]
        fields_text = cells[2]

        signal_tokens = RE_EVENT_TOKEN.findall(signal)
        if not signal_tokens:
            continue
        event = signal_tokens[0]
        variant = signal_tokens[1] if len(signal_tokens) > 1 else None

        field_tokens = RE_EVENT_TOKEN.findall(fields_text)
        rows.append(
            {
                "event": event,
                "variant": variant,
                "threshold_display": _normalize_text(threshold),
                "fields": field_tokens,
            }
        )
    return rows


def _parse_schema_rules(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rules = payload.get("rules")
    else:
        rules = payload
    if not isinstance(rules, list):
        raise ValueError("alarm rules schema must be a list or contain a 'rules' list")

    normalized_rules: list[dict[str, Any]] = []
    for raw in rules:
        if not isinstance(raw, dict):
            raise ValueError("each alarm rule must be an object")
        event = str(raw.get("event", "")).strip()
        if not event:
            raise ValueError("alarm rule event is required")
        variant = raw.get("variant")
        normalized_rules.append(
            {
                "id": str(raw.get("id", event)).strip() or event,
                "event": event,
                "variant": (
                    str(variant).strip()
                    if isinstance(variant, str) and variant.strip()
                    else None
                ),
                "threshold_display": _normalize_text(str(raw.get("threshold_display", ""))),
                "fields": [str(item) for item in raw.get("fields", []) if str(item).strip()],
                "eval": raw.get("eval"),
            }
        )
    return normalized_rules


def parse_structured_log(log_file: Path) -> list[tuple[datetime | None, dict[str, Any]]]:
    if not log_file.exists():
        return []

    records: list[tuple[datetime | None, dict[str, Any]]] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event = payload.get("event")
        if not isinstance(event, str):
            continue

        timestamp = None
        match = RE_TIMESTAMP.match(line)
        if match:
            try:
                timestamp = datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                timestamp = None
        records.append((timestamp, payload))
    return records


def evaluate_sample_alerts(
    *,
    records: list[tuple[datetime | None, dict[str, Any]]],
    rules: list[dict[str, Any]],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    valid_times = [timestamp for timestamp, _ in records if timestamp is not None]
    reference = now or (max(valid_times) if valid_times else None)

    alerts: list[dict[str, Any]] = []
    for rule in rules:
        eval_rule = rule.get("eval")
        if not isinstance(eval_rule, dict):
            continue

        eval_type = str(eval_rule.get("type", "")).strip()
        if eval_type not in {"count_gte", "single_event"}:
            continue

        threshold_count = int(eval_rule.get("count", 1)) if eval_type == "count_gte" else 1
        window_sec = int(eval_rule.get("window_sec", 0))
        event = str(rule.get("event", ""))
        variant = rule.get("variant")

        matched = 0
        for timestamp, payload in records:
            if payload.get("event") != event:
                continue
            if variant is not None and payload.get("health_event") != variant:
                continue
            if reference is not None and window_sec > 0:
                if timestamp is None:
                    continue
                age_sec = (reference - timestamp).total_seconds()
                if age_sec > window_sec:
                    continue
            matched += 1

        alerts.append(
            {
                "id": rule.get("id"),
                "event": event,
                "variant": variant,
                "eval_type": eval_type,
                "window_sec": window_sec,
                "threshold_count": threshold_count,
                "matched": matched,
                "triggered": matched >= threshold_count,
            }
        )
    return alerts


def build_report(
    *,
    schema_path: Path,
    operation_doc_path: Path,
    source_root: Path,
    sample_log_file: Path | None = None,
    event_payload_contract: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    schema_rules = _parse_schema_rules(schema_path)
    operation_rules = _parse_markdown_table_rows(operation_doc_path)
    payload_contract = event_payload_contract or build_event_payload_contract(source_root)

    schema_key_map: dict[str, dict[str, Any]] = {}
    docs_key_map: dict[str, dict[str, Any]] = {}
    duplicate_schema_keys: list[str] = []
    duplicate_operation_keys: list[str] = []

    for rule in schema_rules:
        key = _event_key(rule["event"], rule.get("variant"))
        if key in schema_key_map:
            duplicate_schema_keys.append(key)
        schema_key_map[key] = rule

    for rule in operation_rules:
        key = _event_key(rule["event"], rule.get("variant"))
        if key in docs_key_map:
            duplicate_operation_keys.append(key)
        docs_key_map[key] = rule

    missing_in_operation = sorted(set(schema_key_map) - set(docs_key_map))
    unknown_in_operation = sorted(set(docs_key_map) - set(schema_key_map))

    threshold_mismatches: list[dict[str, str]] = []
    field_mismatches: list[dict[str, Any]] = []
    schema_field_missing_in_code: list[dict[str, Any]] = []

    for key in sorted(set(schema_key_map) & set(docs_key_map)):
        expected = schema_key_map[key]
        actual = docs_key_map[key]
        if expected["threshold_display"] != actual["threshold_display"]:
            threshold_mismatches.append(
                {
                    "key": key,
                    "expected": expected["threshold_display"],
                    "actual": actual["threshold_display"],
                }
            )

        expected_fields = sorted(set(expected["fields"]))
        actual_fields = sorted(set(actual["fields"]))
        if expected_fields != actual_fields:
            field_mismatches.append(
                {
                    "key": key,
                    "expected": expected_fields,
                    "actual": actual_fields,
                }
            )

    for rule in schema_rules:
        event = rule["event"]
        expected_fields = [field for field in rule["fields"] if field]
        available_fields = set(payload_contract.get(event, []))
        missing_fields = sorted(field for field in expected_fields if field not in available_fields)
        if missing_fields:
            schema_field_missing_in_code.append(
                {
                    "key": _event_key(event, rule.get("variant")),
                    "event": event,
                    "missing_fields": missing_fields,
                }
            )

    sample_alerts: list[dict[str, Any]] = []
    if sample_log_file is not None:
        sample_records = parse_structured_log(sample_log_file)
        sample_alerts = evaluate_sample_alerts(records=sample_records, rules=schema_rules)

    passed = not (
        missing_in_operation
        or unknown_in_operation
        or duplicate_schema_keys
        or duplicate_operation_keys
        or threshold_mismatches
        or field_mismatches
        or schema_field_missing_in_code
    )
    return {
        "passed": passed,
        "schema_path": str(schema_path),
        "operation_doc_path": str(operation_doc_path),
        "schema_rules_count": len(schema_rules),
        "operation_rules_count": len(operation_rules),
        "payload_contract_events": len(payload_contract),
        "missing_in_operation": missing_in_operation,
        "unknown_in_operation": unknown_in_operation,
        "duplicate_schema_keys": sorted(set(duplicate_schema_keys)),
        "duplicate_operation_keys": sorted(set(duplicate_operation_keys)),
        "threshold_mismatches": threshold_mismatches,
        "field_mismatches": field_mismatches,
        "schema_field_missing_in_code": schema_field_missing_in_code,
        "sample_alerts": sample_alerts,
    }


def render_markdown(report: dict[str, Any]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Alarm Rules Sync Check",
        "",
        f"- status: `{status}`",
        f"- schema_rules_count: `{report['schema_rules_count']}`",
        f"- operation_rules_count: `{report['operation_rules_count']}`",
        f"- payload_contract_events: `{report['payload_contract_events']}`",
        "",
        f"- missing_in_operation: `{report['missing_in_operation']}`",
        f"- unknown_in_operation: `{report['unknown_in_operation']}`",
        f"- duplicate_schema_keys: `{report['duplicate_schema_keys']}`",
        f"- duplicate_operation_keys: `{report['duplicate_operation_keys']}`",
        f"- threshold_mismatches: `{report['threshold_mismatches']}`",
        f"- field_mismatches: `{report['field_mismatches']}`",
        f"- schema_field_missing_in_code: `{report['schema_field_missing_in_code']}`",
        f"- sample_alerts: `{report['sample_alerts']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate alarm rules schema/docs/code sync.")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("docs/alarm_rules.json"),
        help="Path to alarm rules schema JSON.",
    )
    parser.add_argument(
        "--operation-doc",
        type=Path,
        default=Path("docs/OPERATION.md"),
        help="Path to operation markdown doc.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("app"),
        help="Source root to build event payload contract.",
    )
    parser.add_argument(
        "--sample-log",
        type=Path,
        default=None,
        help="Optional sample log path for rule evaluation preview.",
    )
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    report = build_report(
        schema_path=args.schema,
        operation_doc_path=args.operation_doc,
        source_root=args.source_root,
        sample_log_file=args.sample_log,
    )

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
