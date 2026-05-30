"""Architectural fitness test (RNF-02 / ADR-001, non-negotiable #1).

All arrows point at the domain. The domain depends on nothing below it.
This test parses every module under gnomon.domain and fails if any of them
imports an infrastructure package. It is the executable form of the
dependency rule, guarding against future drift.
"""

import ast
import pathlib

DOMAIN_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "gnomon" / "domain"

INFRA_PACKAGES = {
    "gnomon.targets",
    "gnomon.judge",
    "gnomon.metrics",
    "gnomon.runner",
    "gnomon.reporting",
    "gnomon.config",
    "gnomon.gate",
}


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_domain_imports_no_infrastructure():
    domain_files = list(DOMAIN_DIR.glob("*.py"))
    assert domain_files, "expected domain modules to exist"

    offenders: dict[str, set[str]] = {}
    for path in domain_files:
        imported = _imported_modules(path.read_text())
        bad = {
            mod
            for mod in imported
            for infra in INFRA_PACKAGES
            if mod == infra or mod.startswith(infra + ".")
        }
        if bad:
            offenders[path.name] = bad

    assert not offenders, f"domain must not import infrastructure: {offenders}"
