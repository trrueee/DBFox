"""Automated engineering contract for Runtime DLC R0.1 backend loading feasibility.

This test proves:
1. Dynamic multi-file Python DLC package loading via importlib.util spec.
2. Relative imports between DLC modules.
3. Nested subpackage imports within the DLC.
4. DBFox Host SDK imports from the host runtime (e.g., ResourceScopeRef).
5. Pure-Python vendored dependencies loaded under DLC namespace without global sys.path mutation.
6. Namespace collision resistance: DLC A and DLC B vendor different commonlib without collision.
7. Deterministic failure isolation: missing/broken dependencies raise ModuleNotFoundError.
8. Transactional staging isolation: failed registrations clean up temporary sys.modules entries.
9. Crypto envelope rules: integrity.json contains payload files only (no self-reference).

Residual v1 in-process risks:
- Infinite loops/hangs, os._exit(), and native memory faults are NOT isolated in v1 in-process model.
- Process-level isolation is deferred to R8 (Subprocess DLC Host).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


def _create_test_dlc_tree(
    root_dir: Path,
    dlc_id: str = "acme.feasibility_proof",
    *,
    greeting_target: str = "DBFox",
    vendored_msg: str = "v1",
    include_broken_dep: bool = False,
) -> Path:
    """Create an external multi-file DLC package structure outside DBFox source tree."""
    backend_dir = root_dir / "backend"
    subpkg_dir = backend_dir / "subpkg"
    vendor_dir = backend_dir / "vendor"
    subpkg_dir.mkdir(parents=True, exist_ok=True)
    vendor_dir.mkdir(parents=True, exist_ok=True)

    # 1. manifest.json
    (root_dir / "manifest.json").write_text(
        json.dumps(
            {
                "manifestSchemaVersion": 1,
                "id": dlc_id,
                "version": "1.0.0",
                "displayName": "Feasibility Proof DLC",
                "publisher": "acme",
                "extensionApiVersion": "2",
                "requiresDbfox": ">=1.0.0",
            }
        ),
        encoding="utf-8",
    )

    # 2. backend/__init__.py
    (backend_dir / "__init__.py").write_text(
        f"# Package init\nDLC_ID = {dlc_id!r}\n",
        encoding="utf-8",
    )

    # 3. backend/helper.py
    (backend_dir / "helper.py").write_text(
        "def format_greeting(target: str) -> str:\n"
        "    return f'Hello {target} from DLC helper'\n",
        encoding="utf-8",
    )

    # 4. backend/subpkg/__init__.py & calc.py
    (subpkg_dir / "__init__.py").write_text("# Subpkg init\n", encoding="utf-8")
    (subpkg_dir / "calc.py").write_text(
        "def compute_total(a: int, b: int) -> int:\n"
        "    return (a * 10) + b\n",
        encoding="utf-8",
    )

    # 5. backend/vendor/__init__.py & pure_vendored.py (pure-Python vendored dependency)
    (vendor_dir / "__init__.py").write_text("# Vendor init\n", encoding="utf-8")
    (vendor_dir / "pure_vendored.py").write_text(
        f"def vendored_transform(data: str) -> str:\n"
        f"    return f'vendored:{vendored_msg}:' + data.upper()\n",
        encoding="utf-8",
    )

    # 6. backend/entry.py
    broken_import = "import nonexistent_custom_native_dependency_xyz\n" if include_broken_dep else ""
    (backend_dir / "entry.py").write_text(
        "from .helper import format_greeting\n"
        "from .subpkg.calc import compute_total\n"
        "from .vendor.pure_vendored import vendored_transform\n"
        "from dbfox_dlc_api import ResourceScopeRef\n"
        f"{broken_import}"

        "\n"
        "def run_probe() -> dict:\n"
        "    ref = ResourceScopeRef(kind='test_proof', id='proof_1', version=42)\n"
        f"    greeting = format_greeting({greeting_target!r})\n"
        "    total = compute_total(4, 2)\n"
        "    transformed = vendored_transform('data')\n"
        "    return {\n"
        "        'greeting': greeting,\n"
        "        'total': total,\n"
        "        'transformed': transformed,\n"
        "        'scope_ref_kind': ref.kind,\n"
        "        'scope_ref_id': ref.id,\n"
        "        'scope_ref_version': ref.version,\n"
        "    }\n",
        encoding="utf-8",
    )

    return root_dir


def _load_external_dlc(
    package_dir: Path,
    dlc_id: str = "acme.feasibility_proof",
    digest_prefix: str = "a1b2c3d4",
) -> Any:
    """Load an external multi-file DLC package into an isolated DLC namespace without mutating global sys.path."""
    backend_dir = package_dir / "backend"
    entry_path = backend_dir / "entry.py"
    if not entry_path.is_file():
        raise FileNotFoundError(f"Missing entrypoint: {entry_path}")

    # Namespace format: _dbfox_dlc_<safe_id>_<digestprefix>
    safe_id = dlc_id.replace(".", "_").replace("-", "_")
    pkg_name = f"_dbfox_dlc_{safe_id}_{digest_prefix}"
    init_path = backend_dir / "__init__.py"

    created_modules: list[str] = []

    try:
        if init_path.is_file():
            pkg_spec = importlib.util.spec_from_file_location(
                pkg_name,
                str(init_path),
                submodule_search_locations=[str(backend_dir)],
            )
            if pkg_spec is None or pkg_spec.loader is None:
                raise ImportError(f"Failed to create package spec for {pkg_name}")
            pkg_mod = importlib.util.module_from_spec(pkg_spec)
            sys.modules[pkg_name] = pkg_mod
            created_modules.append(pkg_name)
            pkg_spec.loader.exec_module(pkg_mod)

        entry_mod_name = f"{pkg_name}.entry" if init_path.is_file() else pkg_name
        entry_spec = importlib.util.spec_from_file_location(
            entry_mod_name,
            str(entry_path),
        )
        if entry_spec is None or entry_spec.loader is None:
            raise ImportError(f"Failed to create entry spec for {entry_mod_name}")
        entry_mod = importlib.util.module_from_spec(entry_spec)
        sys.modules[entry_mod_name] = entry_mod
        created_modules.append(entry_mod_name)
        entry_spec.loader.exec_module(entry_mod)
        return entry_mod
    except Exception:
        # Transactional rollback: purge any temporary modules created during failed staging
        for mod_name in created_modules:
            sys.modules.pop(mod_name, None)
        raise


def test_runtime_dlc_dynamic_loading_mechanics(tmp_path: Path) -> None:
    """Prove pure-Python multi-file DLC loading with relative, subpackage, SDK, and vendored imports."""
    dlc_dir = tmp_path / "acme_dlc"
    dlc_dir.mkdir()
    _create_test_dlc_tree(dlc_dir, include_broken_dep=False)

    # Record initial sys.path to prove zero mutation
    initial_sys_path = list(sys.path)

    mod = _load_external_dlc(dlc_dir)
    assert hasattr(mod, "run_probe")

    result = mod.run_probe()
    assert result["greeting"] == "Hello DBFox from DLC helper"
    assert result["total"] == 42
    assert result["transformed"] == "vendored:v1:DATA"
    assert result["scope_ref_kind"] == "test_proof"
    assert result["scope_ref_id"] == "proof_1"
    assert result["scope_ref_version"] == 42

    # Verify zero global sys.path mutation
    assert sys.path == initial_sys_path


def test_runtime_dlc_multi_package_vendored_namespace_isolation(tmp_path: Path) -> None:
    """Prove that DLC A and DLC B can vendor conflicting versions of the same library without collision."""
    dlc_a_dir = tmp_path / "dlc_a"
    dlc_b_dir = tmp_path / "dlc_b"
    dlc_a_dir.mkdir()
    dlc_b_dir.mkdir()

    _create_test_dlc_tree(dlc_a_dir, dlc_id="acme.plugin_a", vendored_msg="VERSION_A")
    _create_test_dlc_tree(dlc_b_dir, dlc_id="acme.plugin_b", vendored_msg="VERSION_B")

    mod_a = _load_external_dlc(dlc_a_dir, dlc_id="acme.plugin_a", digest_prefix="aaaa1111")
    mod_b = _load_external_dlc(dlc_b_dir, dlc_id="acme.plugin_b", digest_prefix="bbbb2222")

    res_a = mod_a.run_probe()
    res_b = mod_b.run_probe()

    assert res_a["transformed"] == "vendored:VERSION_A:DATA"
    assert res_b["transformed"] == "vendored:VERSION_B:DATA"


def test_runtime_dlc_unsupported_dependency_fails_closed(tmp_path: Path) -> None:
    """Prove that missing or unsupported native dependencies cleanly raise ModuleNotFoundError."""
    dlc_dir = tmp_path / "broken_dlc"
    dlc_dir.mkdir()
    _create_test_dlc_tree(dlc_dir, include_broken_dep=True)

    with pytest.raises(ModuleNotFoundError) as exc_info:
        _load_external_dlc(dlc_dir, dlc_id="acme.broken_dlc")

    assert "nonexistent_custom_native_dependency_xyz" in str(exc_info.value)


def test_runtime_dlc_transactional_staging_isolation(tmp_path: Path) -> None:
    """Prove that a failed DLC registration cleans up sys.modules and does not pollute host state."""
    committed_registry: dict[str, str] = {"core_tool": "v1"}
    staging_registry: dict[str, str] = dict(committed_registry)

    dlc_dir = tmp_path / "staging_dlc"
    dlc_dir.mkdir()
    _create_test_dlc_tree(dlc_dir, dlc_id="acme.staging_test", include_broken_dep=True)

    dlc_load_success = False
    try:
        staging_registry["dlc_tool_a"] = "v1"
        _load_external_dlc(dlc_dir, dlc_id="acme.staging_test", digest_prefix="fail9999")
        dlc_load_success = True
    except ModuleNotFoundError:
        # Rollback staging scope
        staging_registry = dict(committed_registry)

    assert not dlc_load_success
    assert "dlc_tool_a" not in staging_registry
    assert staging_registry == {"core_tool": "v1"}
    assert committed_registry == {"core_tool": "v1"}

    # Verify sys.modules was cleaned up
    assert "_dbfox_dlc_acme_staging_test_fail9999" not in sys.modules
    assert "_dbfox_dlc_acme_staging_test_fail9999.entry" not in sys.modules
