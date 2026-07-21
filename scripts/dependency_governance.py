"""Generate a CycloneDX inventory and enforce the DBFox dependency license policy."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DENIED_LICENSE_MARKERS = (
    "AGPL", "GPL-", "GPL ", "SSPL", "BUSL", "BUSINESS SOURCE", "COMMONS CLAUSE",
)


@dataclass(frozen=True)
class Component:
    ecosystem: str
    name: str
    version: str
    license: str

    @property
    def purl(self) -> str:
        namespace = {"node": "npm", "python": "pypi", "rust": "cargo"}[self.ecosystem]
        return f"pkg:{namespace}/{self.name}@{self.version}"


def node_components() -> list[Component]:
    lock = json.loads((ROOT / "desktop" / "package-lock.json").read_text(encoding="utf-8"))
    result: list[Component] = []
    for path, package in lock.get("packages", {}).items():
        if not path or not package.get("version"):
            continue
        name = package.get("name") or path.rsplit("node_modules/", 1)[-1]
        result.append(Component("node", str(name), str(package["version"]), str(package.get("license") or "UNKNOWN")))
    return result


def python_components() -> list[Component]:
    locked = _python_lock_versions(ROOT / "requirements.lock")
    result: list[Component] = []
    installed = {distribution.metadata["Name"].lower().replace("_", "-"): distribution for distribution in importlib.metadata.distributions()}
    for normalized_name, (name, version) in locked.items():
        distribution = installed.get(normalized_name)
        if distribution is None:
            raise RuntimeError(f"Locked Python dependency is not installed: {name}=={version}")
        metadata = distribution.metadata
        license_value = str(metadata.get("License-Expression") or "").strip()
        if not license_value:
            classifiers = metadata.get_all("Classifier") or []
            approved = [value.rsplit("::", 1)[-1].strip() for value in classifiers if "License :: OSI Approved" in value]
            license_value = " OR ".join(approved)
        if not license_value:
            raw = str(metadata.get("License") or "").strip()
            license_value = raw if raw and raw.upper() != "UNKNOWN" else "UNKNOWN"
        result.append(Component("python", name, version, license_value))
    return result


def rust_components() -> list[Component]:
    completed = subprocess.run(
        ["cargo", "metadata", "--locked", "--format-version", "1"],
        cwd=ROOT / "desktop" / "src-tauri",
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    metadata = json.loads(completed.stdout)
    workspace = set(metadata.get("workspace_members") or [])
    result: list[Component] = []
    for package in metadata.get("packages") or []:
        if package.get("id") in workspace:
            continue
        result.append(Component(
            "rust", str(package["name"]), str(package["version"]), str(package.get("license") or "UNKNOWN")
        ))
    return result


def _python_lock_versions(path: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for match in re.finditer(r"(?m)^([A-Za-z0-9_.-]+)==([^\s\\;]+)", path.read_text(encoding="utf-8")):
        name, version = match.groups()
        result[name.lower().replace("_", "-")] = (name, version)
    return result


def validate_licenses(components: Iterable[Component]) -> list[str]:
    failures: list[str] = []
    for component in components:
        normalized = component.license.upper()
        if normalized == "UNKNOWN":
            failures.append(f"{component.purl}: license metadata is missing")
        elif _license_is_denied(normalized):
            failures.append(f"{component.purl}: denied license {component.license}")
    return failures


def _license_is_denied(expression: str) -> bool:
    """Accept an SPDX OR expression when at least one offered license is allowed."""
    alternatives = re.split(r"\s+OR\s+", expression)
    return all(any(marker in alternative for marker in DENIED_LICENSE_MARKERS) for alternative in alternatives)


def cyclonedx_document(components: list[Component]) -> dict[str, object]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:dbfox-dependency-inventory",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "DBFox"}},
        "components": [
            {
                "type": "library",
                "group": component.ecosystem,
                "name": component.name,
                "version": component.version,
                "purl": component.purl,
                "licenses": [{"license": {"name": component.license}}],
            }
            for component in sorted(components, key=lambda item: item.purl)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ecosystem", choices=("node", "python", "rust", "all"), default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    loaders = {"node": node_components, "python": python_components, "rust": rust_components}
    selected = loaders if args.ecosystem == "all" else {args.ecosystem: loaders[args.ecosystem]}
    components = [component for loader in selected.values() for component in loader()]
    failures = validate_licenses(components)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(cyclonedx_document(components), indent=2) + "\n", encoding="utf-8")
    if failures:
        print("Dependency license policy failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Validated {len(components)} locked components for {', '.join(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
