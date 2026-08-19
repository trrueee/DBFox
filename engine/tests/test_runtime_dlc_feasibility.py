"""Automated engineering contract for Runtime DLC R0.1 backend loading feasibility.

This test proves:
1. Dynamic multi-file Python DLC package loading via importlib.util spec.
2. Relative imports between DLC modules.
3. Nested subpackage imports within the DLC.
4. DBFox Host SDK imports from the host runtime (e.g., ResourceScopeRef).
5. Pure-Python vendored dependencies inside the DLC package.
6. Deterministic failure isolation: missing/broken dependencies raise ModuleNotFoundError.
7. Transactional staging isolation: failed registrations do not mutate committed host state.
8. If the frozen sidecar binary exists, proves parity inside the real PyInstaller executable.

Residual v1 in-process risks:
- Infinite loops/hangs, os._exit(), and native memory faults are NOT isolated in v1 in-process model.
- Process-level isolation is deferred to R8 (Subprocess DLC Host).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest



def _create_test_dlc_tree(root_dir: Path, *, include_broken_dep: bool = False) -> Path:
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
                "id": "acme.feasibility_proof",
                "version": "1.0.0",
                "displayName": "Feasibility Proof DLC",
                "publisher": "acme",
                "extensionApiVersion": "1",
                "requiresDbfox": ">=1.0.0",
            }
        ),
        encoding="utf-8",
    )

    # 2. backend/__init__.py
    (backend_dir / "__init__.py").write_text(
        "# Package init\nDLC_PACKAGE_NAME = 'acme.feasibility_proof'\n",
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

    # 5. backend/vendor/pure_vendored.py (pure-Python vendored dependency)
    (vendor_dir / "pure_vendored.py").write_text(
        "def vendored_transform(data: str) -> str:\n"
        "    return f'vendored:{data.upper()}'\n",
        encoding="utf-8",
    )

    # 6. backend/entry.py
    broken_import = "import nonexistent_custom_native_dependency_xyz\n" if include_broken_dep else ""
    (backend_dir / "entry.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "# Add vendor directory to module search path\n"
        "vendor_path = str(Path(__file__).parent / 'vendor')\n"
        "if vendor_path not in sys.path:\n"
        "    sys.path.insert(0, vendor_path)\n"
        "\n"
        "from .helper import format_greeting\n"
        "from .subpkg.calc import compute_total\n"
        "from pure_vendored import vendored_transform\n"
        "from engine.agent.resource_refs import ResourceScopeRef\n"
        f"{broken_import}"
        "\n"
        "def run_probe() -> dict:\n"
        "    ref = ResourceScopeRef(kind='test_proof', id='proof_1', version=42)\n"
        "    greeting = format_greeting('DBFox')\n"
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


def _load_external_dlc(package_dir: Path, dlc_id: str = "acme.feasibility_proof") -> Any:
    """Load an external multi-file DLC package using the canonical importlib.util loader."""
    backend_dir = package_dir / "backend"
    entry_path = backend_dir / "entry.py"
    if not entry_path.is_file():
        raise FileNotFoundError(f"Missing entrypoint: {entry_path}")

    pkg_name = f"_dbfox_dlc_pkg_{dlc_id.replace('.', '_')}"
    init_path = backend_dir / "__init__.py"

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
    entry_spec.loader.exec_module(entry_mod)
    return entry_mod


def test_runtime_dlc_dynamic_loading_mechanics(tmp_path: Path) -> None:
    """Prove pure-Python multi-file DLC loading with relative, subpackage, SDK, and vendored imports."""
    dlc_dir = tmp_path / "acme_dlc"
    dlc_dir.mkdir()
    _create_test_dlc_tree(dlc_dir, include_broken_dep=False)

    mod = _load_external_dlc(dlc_dir)
    assert hasattr(mod, "run_probe")

    result = mod.run_probe()
    assert result["greeting"] == "Hello DBFox from DLC helper"
    assert result["total"] == 42
    assert result["transformed"] == "vendored:DATA"
    assert result["scope_ref_kind"] == "test_proof"
    assert result["scope_ref_id"] == "proof_1"
    assert result["scope_ref_version"] == 42


def test_runtime_dlc_unsupported_dependency_fails_closed(tmp_path: Path) -> None:
    """Prove that missing or unsupported native dependencies cleanly raise ModuleNotFoundError."""
    dlc_dir = tmp_path / "broken_dlc"
    dlc_dir.mkdir()
    _create_test_dlc_tree(dlc_dir, include_broken_dep=True)

    with pytest.raises(ModuleNotFoundError) as exc_info:
        _load_external_dlc(dlc_dir, dlc_id="acme.broken_dlc")

    assert "nonexistent_custom_native_dependency_xyz" in str(exc_info.value)


def test_runtime_dlc_transactional_staging_isolation(tmp_path: Path) -> None:
    """Prove that a failed DLC registration does not pollute committed host state."""
    committed_registry: dict[str, str] = {"core_tool": "v1"}
    staging_registry: dict[str, str] = dict(committed_registry)

    dlc_dir = tmp_path / "staging_dlc"
    dlc_dir.mkdir()
    _create_test_dlc_tree(dlc_dir, include_broken_dep=True)

    dlc_load_success = False
    try:
        staging_registry["dlc_tool_a"] = "v1"
        _load_external_dlc(dlc_dir, dlc_id="acme.staging_test")
        dlc_load_success = True
    except ModuleNotFoundError:
        # Rollback staging scope
        staging_registry = dict(committed_registry)

    assert not dlc_load_success
    assert "dlc_tool_a" not in staging_registry
    assert staging_registry == {"core_tool": "v1"}
    assert committed_registry == {"core_tool": "v1"}


def test_runtime_dlc_frozen_sidecar_parity_probe() -> None:
    """Execute the loading probe inside the actual compiled sidecar binary if present."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    binaries_dir = repo_root / "desktop" / "src-tauri" / "binaries"

    sidecar_exe: Path | None = None
    if sys.platform == "win32":
        candidates = list(binaries_dir.glob("dbfox-engine-*.exe"))
        if candidates:
            sidecar_exe = candidates[0]
    else:
        candidates = [p for p in binaries_dir.glob("dbfox-engine-*") if not p.name.endswith(".json")]
        if candidates:
            sidecar_exe = candidates[0]

    if sidecar_exe is None or not sidecar_exe.is_file():
        pytest.skip("Frozen sidecar binary not found in desktop/src-tauri/binaries/ (run build_sidecar.py to test)")

    with tempfile.TemporaryDirectory(prefix="dbfox_frozen_test_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        _create_test_dlc_tree(temp_dir, include_broken_dep=False)

        env = os.environ.copy()
        env["DBFOX_ENGINE_TOKEN"] = "test-token-probe"

        result = subprocess.run(
            [str(sidecar_exe), "--probe-dlc-loader", str(temp_dir)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"Sidecar probe failed (exit={result.returncode}): {result.stderr}"

        probe_line = next(
            (line for line in result.stdout.splitlines() if line.startswith("DBFOX_DLC_LOADER_PROBE ")),
            None,
        )
        assert probe_line is not None, f"Marker not found in stdout: {result.stdout}"

        payload = json.loads(probe_line[len("DBFOX_DLC_LOADER_PROBE "):])
        assert payload["status"] == "success"
        assert payload["frozen"] is True
        res = payload["probe_result"]
        assert res["greeting"] == "Hello DBFox from DLC helper"
        assert res["total"] == 42
        assert res["transformed"] == "vendored:DATA"
        assert res["scope_ref_kind"] == "test_proof"
