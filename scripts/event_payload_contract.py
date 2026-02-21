from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from app.observability import events


def _resolve_event_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "events"
    ):
        value = getattr(events, node.attr, None)
        if isinstance(value, str):
            return value
    return None


def _collect_payload_fields(path: Path) -> dict[str, set[str]]:
    payload_fields: dict[str, set[str]] = {}
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "log_event":
            continue
        if not node.args:
            continue

        event_name = _resolve_event_name(node.args[0])
        if not event_name:
            continue

        fields = payload_fields.setdefault(event_name, set())
        for keyword in node.keywords:
            if keyword.arg:
                fields.add(keyword.arg)
    return payload_fields


def build_event_payload_contract(source_root: Path = Path("app")) -> dict[str, list[str]]:
    contract: dict[str, set[str]] = {}
    for path in sorted(source_root.rglob("*.py")):
        for event_name, fields in _collect_payload_fields(path).items():
            merged = contract.setdefault(event_name, set())
            merged.update(fields)
    return {event: sorted(fields) for event, fields in sorted(contract.items())}


def render_markdown(contract: dict[str, list[str]]) -> str:
    lines = [
        "## Event Payload Contract",
        "",
        f"- tracked_events: `{len(contract)}`",
        "",
        "| event | payload_keys |",
        "|---|---|",
    ]
    for event, fields in contract.items():
        lines.append(f"| `{event}` | `{fields}` |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build event payload contract snapshot.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("app"),
        help="Path to source root to scan.",
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

    contract = build_event_payload_contract(args.source_root)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    markdown = render_markdown(contract)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
