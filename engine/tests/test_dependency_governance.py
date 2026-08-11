from email.message import Message
from pathlib import Path

from packaging.markers import default_environment

from scripts.dependency_governance import (
    Component,
    _python_lock_versions,
    node_components,
    python_components,
    validate_licenses,
)
from scripts import dependency_governance


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


def test_python_lock_inventory_honors_standard_environment_markers(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "common==1.0 \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n"
        "windows-only==2.0 ; sys_platform == 'win32' \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "posix-only==3.0 ; sys_platform != 'win32' \\\n"
        "    --hash=sha256:" + "c" * 64 + "\n",
        encoding="utf-8",
    )

    windows_environment = default_environment()
    windows_environment["sys_platform"] = "win32"
    linux_environment = default_environment()
    linux_environment["sys_platform"] = "linux"

    assert set(
        _python_lock_versions(lock, marker_environment=windows_environment)
    ) == {"common", "windows-only"}
    assert set(
        _python_lock_versions(lock, marker_environment=linux_environment)
    ) == {"common", "posix-only"}


def test_python_inventory_uses_pep_503_canonical_distribution_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "requirements.lock").write_text(
        "jaraco-classes==3.4.0 \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    metadata = Message()
    metadata["Name"] = "jaraco.classes"
    metadata["Version"] = "3.4.0"
    metadata["License-Expression"] = "MIT"
    distribution = type("Distribution", (), {"metadata": metadata})()
    monkeypatch.setattr(dependency_governance, "ROOT", tmp_path)
    monkeypatch.setattr(
        dependency_governance.importlib.metadata,
        "distributions",
        lambda: [distribution],
    )

    assert python_components() == [
        Component("python", "jaraco-classes", "3.4.0", "MIT")
    ]
