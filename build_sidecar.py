#!/usr/bin/env python
"""Build the DBFox Python engine into a standalone sidecar binary.

This script:
  1. Builds the engine with PyInstaller inside a locked build environment
  2. Copies the binary to desktop/src-tauri/binaries/ with the correct
     target-triplet filename that Tauri's externalBin expects

Development credentials are generated only by dev.ps1/dev.sh or the explicit
--token-only development command. A release build never writes frontend env.

Usage:
    python build_sidecar.py              # full build
    python build_sidecar.py --token-only # generate token files only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.dev_environment import generate_dev_token, write_frontend_env

ROOT = Path(__file__).resolve().parent
ENGINE_DIR = ROOT / "engine"
DESKTOP_DIR = ROOT / "desktop"
BINARIES_DIR = DESKTOP_DIR / "src-tauri" / "binaries"
BUILD_VENV = ROOT / ".build_venv"
BUILD_LOCK = ROOT / "requirements-build.lock"
RUNTIME_MANIFEST_PATH = BINARIES_DIR / "dbfox-engine-runtime-manifest.json"
MINIMUM_SQLITE_VERSION = (3, 51, 3)
TARGET_SQLITE_VERSION = "3.53.4"
RUNTIME_MANIFEST_MARKER = "DBFOX_RUNTIME_MANIFEST "


def get_target_triplet() -> str:
    """Return rustc's official host tuple and fail closed when unavailable."""
    command = ["rustc", "--print", "host-tuple"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise RuntimeError(
            "Failed to run `rustc --print host-tuple`. Install the Rust toolchain "
            f"and ensure rustc is on PATH: {error}"
        ) from error
    target = result.stdout.strip()
    if result.returncode != 0 or not target:
        stderr = result.stderr.strip() or "no stderr"
        raise RuntimeError(
            "`rustc --print host-tuple` failed "
            f"(exit={result.returncode}, stderr={stderr}). Install or repair the "
            "Rust toolchain before building a release."
        )
    return target

# Must match the dependencies in requirements.txt that PyInstaller
# cannot auto-detect (lazy imports, dynamic loaders, etc.)
HIDDEN_IMPORTS = [
    "uvicorn",
    "sqlalchemy",
    "pydantic",
    "fastapi",
    "watchfiles",
    "alembic",
    "psycopg2",
    "duckdb",
    "pymysql",
    "sshtunnel",
    "keyring",
    "sqlglot",
    "httpx",
    "dotenv",
    "openai",
]

SIDECAR_RUNTIME_EXCLUDED_DIRS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "fixtures",
    "tests",
}

SIDECAR_RUNTIME_EXCLUDED_FILE_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
)


def _venv_python() -> str:
    """Return the python executable inside .build_venv, or fail."""
    if sys.platform == "win32":
        exe = str(BUILD_VENV / "Scripts" / "python.exe")
    else:
        exe = str(BUILD_VENV / "bin" / "python")
    if not Path(exe).exists():
        print(
            f"  [FAIL] 构建虚拟环境未找到: {BUILD_VENV}\n"
            f"  请先创建并安装依赖:\n"
            f"    python -m venv {BUILD_VENV}\n"
            f"    uv pip sync requirements-build.lock --python {exe}",
            file=sys.stderr,
        )
        sys.exit(1)
    return exe


def generate_token() -> str:
    return generate_dev_token()


def sync_build_environment(python_exe: str) -> None:
    uv_exe = shutil.which("uv")
    if not BUILD_LOCK.exists():
        print(f"  [FAIL] Build lock file not found: {BUILD_LOCK}", file=sys.stderr)
        sys.exit(1)
    if uv_exe is None:
        print(
            "  [FAIL] Release builds require uv for exact environment sync. "
            "Install it with `python -m pip install uv` and retry.",
            file=sys.stderr,
        )
        sys.exit(1)
    command = [uv_exe, "pip", "sync", str(BUILD_LOCK), "--python", python_exe]
    result = subprocess.run(
        command,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("  [FAIL] Locked build environment sync failed", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"  [OK] Synced from {BUILD_LOCK.name} with uv pip sync")


def write_env_local(token: str) -> Path:
    path = write_frontend_env(token, desktop_dir=DESKTOP_DIR)
    print(f"  [OK] {path}")
    return path


def _ignore_sidecar_runtime(src: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(src) / name
        if path.is_dir() and name in SIDECAR_RUNTIME_EXCLUDED_DIRS:
            ignored.add(name)
            continue
        if path.is_file() and name.endswith(SIDECAR_RUNTIME_EXCLUDED_FILE_SUFFIXES):
            ignored.add(name)
    return ignored


def prepare_sidecar_engine_tree(work_dir: Path) -> Path:
    """Stage only runtime engine files for PyInstaller --add-data."""
    staging_root = work_dir / "_runtime_data"
    staged_engine = staging_root / "engine"
    shutil.rmtree(staging_root, ignore_errors=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ENGINE_DIR, staged_engine, ignore=_ignore_sidecar_runtime)
    return staged_engine


def build_pyinstaller(python_exe: str) -> Path:
    dist_dir = ROOT / "pyinstaller_dist"
    work_dir = ROOT / "pyinstaller_build"
    spec_paths = (ROOT / "dbfox-engine.spec", ROOT / "dbfox_engine.spec")

    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    for spec_path in spec_paths:
        spec_path.unlink(missing_ok=True)
    staged_engine = prepare_sidecar_engine_tree(work_dir)

    cmd = [
        python_exe, "-m", "PyInstaller",
        "--onefile",
        # The desktop supervisor reads a machine protocol from stdout
        # (DBFOX_ENGINE_READY / DBFOX_ENGINE_STAGE).  Keep real stdio handles;
        # the Rust parent suppresses the Windows console window when spawning.
        "--console",
        "--name", "dbfox-engine",
        "--distpath", str(dist_dir),
        "--workpath", str(work_dir),
        "--add-data", f"{staged_engine}{os.pathsep}engine",
        "--add-data", f"{ROOT / 'alembic.ini'}{os.pathsep}.",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]
    cmd.append(str(ENGINE_DIR / "main.py"))

    print("  -> Running PyInstaller (venv: {})...".format(python_exe))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("  [FAIL] PyInstaller build failed", file=sys.stderr)
        sys.exit(result.returncode)

    built_name = "dbfox-engine.exe" if sys.platform == "win32" else "dbfox-engine"
    built = dist_dir / built_name
    if not built.exists():
        print(f"  [FAIL] Expected binary not found: {built}", file=sys.stderr)
        sys.exit(1)

    size_mb = built.stat().st_size / 1_048_576
    print(f"  [OK] Built {size_mb:.0f} MB binary")
    return built


def install_sidecar(binary: Path) -> Path:
    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    triplet = get_target_triplet()
    name = f"dbfox-engine-{triplet}"
    if sys.platform == "win32":
        name += ".exe"
    dest = BINARIES_DIR / name
    shutil.copy2(binary, dest)
    print(f"  [OK] Sidecar -> {dest}")
    return dest


def probe_sidecar_runtime(binary: Path) -> dict[str, object]:
    """Ask the final executable—not the build interpreter—what it loaded."""
    with tempfile.TemporaryDirectory(prefix="dbfox-sidecar-probe-") as runtime_dir:
        env = os.environ.copy()
        env["DBFOX_ENGINE_TOKEN"] = generate_token()
        env["DBFOX_RUNTIME_DIR"] = runtime_dir
        result = subprocess.run(
            [str(binary), "--runtime-manifest"],
            cwd=str(binary.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
    if result.returncode != 0:
        raise RuntimeError(
            "Frozen sidecar runtime probe failed "
            f"(exit={result.returncode}): {result.stderr[-2000:]}"
        )
    manifest_line = next(
        (line for line in reversed(result.stdout.splitlines()) if line.startswith(RUNTIME_MANIFEST_MARKER)),
        None,
    )
    if manifest_line is None:
        raise RuntimeError("Frozen sidecar did not emit DBFOX_RUNTIME_MANIFEST")
    try:
        manifest = json.loads(manifest_line[len(RUNTIME_MANIFEST_MARKER):])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Frozen sidecar emitted invalid runtime manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("Frozen sidecar runtime manifest must be a JSON object")
    validate_runtime_manifest(manifest)
    return manifest


def validate_runtime_manifest(manifest: dict[str, object]) -> None:
    if manifest.get("schema_version") != 1:
        raise RuntimeError("Unsupported sidecar runtime manifest schema")
    version_raw = manifest.get("sqlite_version_info")
    if not isinstance(version_raw, list) or len(version_raw) < 3:
        raise RuntimeError("Sidecar runtime manifest has no valid SQLite version tuple")
    try:
        version = tuple(int(part) for part in version_raw[:3])
    except (TypeError, ValueError) as error:
        raise RuntimeError("Sidecar SQLite version tuple is invalid") from error
    if version < MINIMUM_SQLITE_VERSION:
        actual = ".".join(str(part) for part in version)
        minimum = ".".join(str(part) for part in MINIMUM_SQLITE_VERSION)
        raise RuntimeError(
            f"Release blocked: final sidecar uses SQLite {actual}; minimum is {minimum} "
            f"and the current upgrade target is {TARGET_SQLITE_VERSION}."
        )
    if not manifest.get("sqlite_source_id") or not manifest.get("sqlite_compile_options"):
        raise RuntimeError("Sidecar runtime manifest is missing SQLite provenance")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_artifact_manifest(binary: Path, runtime: dict[str, object]) -> Path:
    artifact = {
        "schema_version": 1,
        "target_triplet": get_target_triplet(),
        "sidecar_filename": binary.name,
        "sidecar_sha256": _sha256(binary),
        "minimum_sqlite_version": ".".join(str(part) for part in MINIMUM_SQLITE_VERSION),
        "target_sqlite_version": TARGET_SQLITE_VERSION,
        "runtime": runtime,
    }
    RUNTIME_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RUNTIME_MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(RUNTIME_MANIFEST_PATH)
    print(f"  [OK] Runtime manifest -> {RUNTIME_MANIFEST_PATH}")
    return RUNTIME_MANIFEST_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DBFox engine sidecar")
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="Only generate token files, skip PyInstaller build",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("DBFox Sidecar Builder")
    print("=" * 55)

    # Validate build prerequisites before producing any generated credential
    # material.  A failed package build must not leave a stale dev token behind.
    python_exe = None if args.token_only else _venv_python()

    if args.token_only:
        token = generate_token()
        print(f"\n[1/1] Dev token ({len(token)} hex chars)")
        write_env_local(token)
        print("\n  Done (token-only mode).")
        return

    assert python_exe is not None
    print("\n[1/4] Sync locked build environment")
    sync_build_environment(python_exe)

    print("\n[2/4] PyInstaller build")
    binary = build_pyinstaller(python_exe)

    print("\n[3/4] Install to Tauri binaries")
    dest = install_sidecar(binary)

    print("\n[4/4] Probe final sidecar and enforce SQLite release policy")
    try:
        runtime_manifest = probe_sidecar_runtime(dest)
        write_artifact_manifest(dest, runtime_manifest)
    except Exception as error:
        dest.unlink(missing_ok=True)
        print(f"  [FAIL] {error}", file=sys.stderr)
        sys.exit(1)

    shutil.rmtree(ROOT / "pyinstaller_dist", ignore_errors=True)
    shutil.rmtree(ROOT / "pyinstaller_build", ignore_errors=True)
    (ROOT / "dbfox-engine.spec").unlink(missing_ok=True)
    (ROOT / "dbfox_engine.spec").unlink(missing_ok=True)

    print("\n" + "=" * 55)
    print("Sidecar build complete.")
    print(f"  {dest}")
    print("  Next: cd desktop && npm run tauri -- build")
    print("=" * 55)


if __name__ == "__main__":
    main()
