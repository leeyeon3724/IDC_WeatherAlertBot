from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = PROJECT_ROOT / "app"
LEGACY_MODULE = "app.domain.code_maps"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 and node.module is not None:
                continue
            if node.module is not None:
                imported.add(node.module)

    return imported


def test_runtime_modules_do_not_depend_on_legacy_code_maps() -> None:
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.name == "code_maps.py":
            continue
        imports = _imported_modules(path)
        if LEGACY_MODULE in imports:
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert offenders == []
