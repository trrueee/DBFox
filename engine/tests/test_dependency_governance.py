from pathlib import Path

from scripts.dependency_governance import Component, node_components, validate_licenses


def test_node_lock_has_only_declared_non_denied_licenses() -> None:
    components = node_components()
    assert len(components) > 500
    assert validate_licenses(components) == []


def test_license_gate_rejects_unknown_and_strong_copyleft() -> None:
    failures = validate_licenses([
        Component("node", "unknown", "1", "UNKNOWN"),
        Component("python", "copyleft", "1", "AGPL-3.0-only"),
    ])
    assert len(failures) == 2


def test_dependency_governance_is_lockfile_only_for_node() -> None:
    source = Path("scripts/dependency_governance.py").read_text(encoding="utf-8")
    assert "package-lock.json" in source
    assert "npm install" not in source
