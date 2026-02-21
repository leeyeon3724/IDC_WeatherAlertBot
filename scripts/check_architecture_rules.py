from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

KNOWN_LAYERS = {
    "domain",
    "services",
    "repositories",
    "usecases",
    "entrypoints",
    "observability",
}

DISALLOWED_TARGETS_BY_SOURCE = {
    "domain": {"services", "repositories", "usecases", "entrypoints", "observability"},
    "services": {"repositories", "usecases", "entrypoints"},
    "repositories": {"services", "usecases", "entrypoints"},
    "usecases": {"entrypoints"},
}


@dataclass(frozen=True)
class ImportViolation:
    source_module: str
    target_module: str
    lineno: int
    reason: str


def module_name_from_path(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    return ".".join(relative.parts)


def layer_of(module_name: str) -> str:
    parts = module_name.split(".")
    if len(parts) < 2:
        return "core"
    layer = parts[1]
    if layer in KNOWN_LAYERS:
        return layer
    return "core"


def normalize_imported_modules(node: ast.AST) -> list[str]:
    modules: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            modules.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.level != 0:
            return []
        if node.module:
            modules.append(node.module)
    return modules


def collect_violations(project_root: Path) -> list[ImportViolation]:
    app_root = project_root / "app"
    violations: list[ImportViolation] = []

    for path in sorted(app_root.rglob("*.py")):
        source_module = module_name_from_path(path, project_root)
        source_layer = layer_of(source_module)
        if source_layer not in DISALLOWED_TARGETS_BY_SOURCE:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported_modules = normalize_imported_modules(node)
            if not imported_modules:
                continue
            for imported_module in imported_modules:
                if not imported_module.startswith("app."):
                    continue
                target_layer = layer_of(imported_module)
                if target_layer in DISALLOWED_TARGETS_BY_SOURCE[source_layer]:
                    violations.append(
                        ImportViolation(
                            source_module=source_module,
                            target_module=imported_module,
                            lineno=getattr(node, "lineno", 0),
                            reason=(
                                f"layer '{source_layer}' must not depend on "
                                f"layer '{target_layer}'"
                            ),
                        )
                    )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate architecture import rules.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("."),
        help="Project root path containing app/.",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    violations = collect_violations(project_root)
    if not violations:
        print("architecture rules check passed")
        return 0

    print("architecture rules check failed")
    for violation in violations:
        print(
            f"- {violation.source_module}:{violation.lineno} -> "
            f"{violation.target_module} ({violation.reason})"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
