from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_rules import collect_violations


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_violations_allows_valid_dependencies(tmp_path: Path) -> None:
    _write(tmp_path / "app" / "domain" / "models.py", "from __future__ import annotations\n")
    _write(
        tmp_path / "app" / "usecases" / "process.py",
        "from app.domain.models import AlertEvent\n",
    )
    violations = collect_violations(tmp_path)
    assert violations == []


def test_collect_violations_detects_domain_to_services_dependency(tmp_path: Path) -> None:
    _write(
        tmp_path / "app" / "domain" / "broken.py",
        "from app.services.notifier import DoorayNotifier\n",
    )
    violations = collect_violations(tmp_path)
    assert len(violations) == 1
    violation = violations[0]
    assert violation.source_module == "app.domain.broken"
    assert violation.target_module == "app.services.notifier"
