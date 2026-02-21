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


class _PayloadContractVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.payload_fields: dict[str, set[str]] = {}
        self._scope_stack: list[dict[str, set[str]]] = [{}]

    @property
    def _scope(self) -> dict[str, set[str]]:
        return self._scope_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope_stack.append({})
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope_stack.append({})
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        keys = _dict_literal_keys(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if keys is not None:
                    self._scope[target.id] = keys
                else:
                    self._scope.pop(target.id, None)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            keys = _dict_literal_keys(node.value) if node.value is not None else None
            if keys is not None:
                self._scope[node.target.id] = keys
            else:
                self._scope.pop(node.target.id, None)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "log_event" and node.args:
            event_name = _resolve_event_name(node.args[0])
            if event_name:
                fields = self.payload_fields.setdefault(event_name, set())
                for keyword in node.keywords:
                    if keyword.arg:
                        fields.add(keyword.arg)
                        continue
                    unpacked = _resolve_dict_unpack_keys(keyword.value, self._scope_stack)
                    fields.update(unpacked)
        self.generic_visit(node)


def _dict_literal_keys(value: ast.AST | None) -> set[str] | None:
    if not isinstance(value, ast.Dict):
        return None
    keys: set[str] = set()
    for key in value.keys:
        if key is None:
            return None
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return None
        keys.add(key.value)
    return keys


def _resolve_dict_unpack_keys(value: ast.AST, scope_stack: list[dict[str, set[str]]]) -> set[str]:
    keys = _dict_literal_keys(value)
    if keys is not None:
        return keys
    if isinstance(value, ast.Name):
        for scope in reversed(scope_stack):
            if value.id in scope:
                return set(scope[value.id])
    return set()


def _collect_payload_fields(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _PayloadContractVisitor()
    visitor.visit(tree)
    return visitor.payload_fields


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
