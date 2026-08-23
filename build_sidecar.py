#!/usr/bin/env python
"""Build the DBFox Python engine into a standalone sidecar binary.

This script:
  1. Builds the engine with PyInstaller inside a locked build environment
  2. Copies the binary to desktop/electron-resources/sidecar/ using the
     fixed filename consumed from Electron's process.resourcesPath

Development credentials are generated only by dev.ps1/dev.sh through
scripts/dev_environment.py. This builder never writes frontend env.

Usage:
    python build_sidecar.py                              # full build
    python build_sidecar.py --refresh-artifact-manifest # after OS code signing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.dev_environment import generate_dev_token

ROOT = Path(__file__).resolve().parent
ENGINE_DIR = ROOT / "engine"
DESKTOP_DIR = ROOT / "desktop"
BINARIES_DIR = DESKTOP_DIR / "electron-resources" / "sidecar"
SYSTEM_DLCS_DIR = DESKTOP_DIR / "electron-resources" / "system-dlcs"
BUILD_VENV = ROOT / ".build_venv"
BUILD_LOCK = ROOT / "requirements-build.lock"
SIDECAR_PYTHON_VERSION_PATH = ROOT / ".sidecar-python-version"
SIDECAR_PYTHON_BUILD_PATH = ROOT / ".sidecar-python-build"
RUNTIME_MANIFEST_PATH = BINARIES_DIR / "dbfox-engine-runtime-manifest.json"
BUILD_PROVENANCE_FILENAME = "_build_provenance.json"
ARTIFACT_MANIFEST_SCHEMA_VERSION = 3
MINIMUM_SQLITE_VERSION = (3, 51, 3)
TARGET_SQLITE_VERSION = "3.53.4"
RUNTIME_MANIFEST_MARKER = "DBFOX_RUNTIME_MANIFEST "
RELEASE_CONTRACTS_MARKER = "DBFOX_RELEASE_CONTRACTS "
KEY_BUILD_PACKAGES = (
    "alembic",
    "fastapi",
    "openai",
    "pydantic",
    "pyinstaller",
    "sqlalchemy",
    "sqlglot",
)


def get_target_triplet(
    *, system: str | None = None, machine: str | None = None
) -> str:
    """Return DBFox's explicit Sidecar target without depending on Rust."""

    selected_system = (system or platform.system()).lower()
    selected_machine = (machine or platform.machine()).lower()
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(selected_machine)
    suffix = {
        "windows": "pc-windows-msvc",
        "darwin": "apple-darwin",
        "linux": "unknown-linux-gnu",
    }.get(selected_system)
    if architecture is None or suffix is None:
        raise RuntimeError(
            "Unsupported DBFox Sidecar target: "
            f"system={selected_system or 'unknown'}, machine={selected_machine or 'unknown'}"
        )
    return f"{architecture}-{suffix}"


def sidecar_python_version() -> str:
    """Return the repository-pinned production Sidecar CPython version."""

    if not SIDECAR_PYTHON_VERSION_PATH.is_file():
        raise RuntimeError(
            f"Sidecar Python version file is missing: {SIDECAR_PYTHON_VERSION_PATH}"
        )
    version = SIDECAR_PYTHON_VERSION_PATH.read_text(encoding="utf-8").strip()
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise RuntimeError("Sidecar Python version must be an exact X.Y.Z version")
    return version


def sidecar_python_build() -> str:
    """Return the pinned python-build-standalone build date used by uv."""

    if not SIDECAR_PYTHON_BUILD_PATH.is_file():
        raise RuntimeError(
            f"Sidecar Python build file is missing: {SIDECAR_PYTHON_BUILD_PATH}"
        )
    build = SIDECAR_PYTHON_BUILD_PATH.read_text(encoding="utf-8").strip()
    if len(build) != 8 or not build.isdigit():
        raise RuntimeError("Sidecar Python build must be an exact YYYYMMDD value")
    return build

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
    # SQLGlot resolves dialect modules with importlib at runtime, which static
    # PyInstaller analysis cannot discover.  Bundle only DBFox's supported
    # dialects instead of collecting SQLGlot's entire dialect package.
    "sqlglot.dialects.mysql",
    "sqlglot.dialects.postgres",
    "sqlglot.dialects.sqlite",
    "httpx",
    "dotenv",
    "openai",
    "dbfox_dlc_api",
    "engine.dlc",
    "engine.dlc.api",
    "engine.dlc.host",
    "engine.dlc.loader",
    "engine.dlc.compiler",
    "engine.dlc.snapshot",
    "engine.dlc.trust",
    "engine.dlc.errors",
    "engine.dlc.manifest",
    "engine.dlc.registry",
    "engine.dlc.integrity",
    "engine.dlc.compat",
    "engine.api.dlc_operations",
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


def build_system_dlc_release_bundle(
    python_exe: str,
    private_key_path: Path,
) -> Path:
    """Build signed official DLCs before freezing their trust pins into Sidecar."""

    resolved_key = private_key_path.expanduser().resolve(strict=True)
    command = [
        python_exe,
        "-m",
        "scripts.build_system_dlc_bundle",
        "--output-dir",
        str(SYSTEM_DLCS_DIR),
        "--private-key",
        str(resolved_key),
    ]
    result = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Unable to build signed System DLC release bundle: "
            f"{result.stderr[-2000:]}"
        )
    manifest = SYSTEM_DLCS_DIR / "system-dlcs.json"
    if not manifest.is_file():
        raise RuntimeError("System DLC builder did not produce its pinned manifest")
    print(f"  [OK] System DLC bundle -> {SYSTEM_DLCS_DIR}")
    return manifest


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


def _source_tree_sha256(root: Path) -> str:
    """Hash the exact runtime source set copied into the frozen Sidecar."""

    digest = hashlib.sha256()
    files: list[tuple[str, Path]] = []
    for source_path in root.rglob("*"):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(root)
        if any(part in SIDECAR_RUNTIME_EXCLUDED_DIRS for part in relative.parts[:-1]):
            continue
        if source_path.name == BUILD_PROVENANCE_FILENAME:
            continue
        if source_path.name.endswith(SIDECAR_RUNTIME_EXCLUDED_FILE_SUFFIXES):
            continue
        files.append((relative.as_posix(), source_path))
    for relative_name, source_path in sorted(files):
        digest.update(relative_name.encode("utf-8"))
        digest.update(b"\0")
        with source_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _git_source_facts() -> dict[str, object]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    unstaged = subprocess.run(
        ["git", "diff", "--quiet", "--ignore-submodules", "--"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--ignore-submodules", "--"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    revision = commit.stdout.strip().lower()
    if commit.returncode != 0 or len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise RuntimeError("Unable to resolve the Git commit for Sidecar provenance")
    if unstaged.returncode not in (0, 1) or staged.returncode not in (0, 1):
        raise RuntimeError("Unable to inspect tracked Git changes for Sidecar provenance")
    if untracked.returncode != 0:
        raise RuntimeError("Unable to inspect the Git worktree for Sidecar provenance")
    return {
        "source_git_commit": revision,
        "source_git_dirty": (
            unstaged.returncode == 1
            or staged.returncode == 1
            or bool(untracked.stdout)
        ),
    }


def _build_environment_facts(python_exe: str) -> dict[str, object]:
    package_literal = json.dumps(KEY_BUILD_PACKAGES)
    command = [
        python_exe,
        "-c",
        (
            "import importlib.metadata as metadata, json, platform, sys; "
            "from pathlib import Path; "
            f"names = {package_literal}; "
            "build_path = Path(sys.base_prefix) / 'BUILD'; "
            "print(json.dumps({'python_version': platform.python_version(), "
            "'python_build': build_path.read_text(encoding='utf-8').strip() "
            "if build_path.is_file() else None, "
            "'packages': {name: metadata.version(name) for name in names}}, "
            "sort_keys=True))"
        ),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "Unable to inspect the locked Sidecar build environment "
            f"(exit={result.returncode}): {result.stderr[-1000:]}"
        )
    try:
        facts = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Sidecar build environment emitted invalid provenance") from error
    if not isinstance(facts, dict) or not isinstance(facts.get("packages"), dict):
        raise RuntimeError("Sidecar build environment provenance is incomplete")
    return facts


def collect_build_provenance(python_exe: str) -> dict[str, object]:
    """Bind the exact interpreter and lock used by the PyInstaller build."""

    expected_python = sidecar_python_version()
    expected_build = sidecar_python_build()
    facts = _build_environment_facts(python_exe)
    actual_python = str(facts.get("python_version") or "")
    if actual_python != expected_python:
        raise RuntimeError(
            "Sidecar build interpreter does not match the production pin: "
            f"expected {expected_python}, got {actual_python or 'unknown'}"
        )
    actual_build = str(facts.get("python_build") or "")
    if actual_build != expected_build:
        raise RuntimeError(
            "Sidecar build interpreter does not match the pinned "
            "python-build-standalone build: "
            f"expected {expected_build}, got {actual_build or 'unreported'}"
        )
    if not BUILD_LOCK.is_file():
        raise RuntimeError(f"Build lock file not found: {BUILD_LOCK}")
    return {
        "schema_version": 2,
        "python_version": actual_python,
        "python_build": actual_build,
        "lock_file": BUILD_LOCK.name,
        "lock_sha256": _sha256(BUILD_LOCK),
        "packages": facts["packages"],
        **_git_source_facts(),
        "engine_source_sha256": _source_tree_sha256(ENGINE_DIR),
    }


def prepare_sidecar_engine_tree(
    work_dir: Path,
    provenance: dict[str, object],
    system_dlc_manifest: Path,
) -> Path:
    """Stage only runtime engine files for PyInstaller --add-data."""
    staging_root = work_dir / "_runtime_data"
    staged_engine = staging_root / "engine"
    shutil.rmtree(staging_root, ignore_errors=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ENGINE_DIR, staged_engine, ignore=_ignore_sidecar_runtime)
    (staged_engine / BUILD_PROVENANCE_FILENAME).write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(system_dlc_manifest, staged_engine / "_system_dlc_bundle.json")
    return staged_engine


def build_pyinstaller(python_exe: str, system_dlc_manifest: Path) -> Path:
    dist_dir = ROOT / "pyinstaller_dist"
    work_dir = ROOT / "pyinstaller_build"
    spec_paths = (ROOT / "dbfox-engine.spec", ROOT / "dbfox_engine.spec")

    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    for spec_path in spec_paths:
        spec_path.unlink(missing_ok=True)
    provenance = collect_build_provenance(python_exe)
    staged_engine = prepare_sidecar_engine_tree(
        work_dir,
        provenance,
        system_dlc_manifest,
    )

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
        "--add-data", f"{ROOT / 'dbfox_dlc_api.py'}{os.pathsep}.",
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
    name = "dbfox-engine.exe" if sys.platform == "win32" else "dbfox-engine"
    dest = BINARIES_DIR / name
    shutil.copy2(binary, dest)
    print(f"  [OK] Sidecar -> {dest}")
    return dest


def _probe_sidecar_json(
    binary: Path,
    *,
    argument: str,
    marker: str,
    label: str,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="dbfox-sidecar-probe-") as runtime_dir:
        env = os.environ.copy()
        env["DBFOX_ENGINE_TOKEN"] = generate_dev_token()
        env["DBFOX_RUNTIME_DIR"] = runtime_dir
        result = subprocess.run(
            [str(binary), argument],
            cwd=str(binary.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Frozen sidecar {label} probe failed "
            f"(exit={result.returncode}): {result.stderr[-2000:]}"
        )
    payload_line = next(
        (line for line in reversed(result.stdout.splitlines()) if line.startswith(marker)),
        None,
    )
    if payload_line is None:
        raise RuntimeError(f"Frozen sidecar did not emit {marker.strip()}")
    try:
        payload = json.loads(payload_line[len(marker):])
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Frozen sidecar emitted invalid {label}: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"Frozen sidecar {label} must be a JSON object")
    return payload


def probe_sidecar_runtime(binary: Path) -> dict[str, object]:
    """Ask the final executable—not the build interpreter—what it loaded."""

    manifest = _probe_sidecar_json(
        binary,
        argument="--runtime-manifest",
        marker=RUNTIME_MANIFEST_MARKER,
        label="runtime manifest",
    )
    validate_runtime_manifest(manifest)
    return manifest


def probe_sidecar_release_contracts(binary: Path) -> dict[str, object]:
    contracts = _probe_sidecar_json(
        binary,
        argument="--release-contracts",
        marker=RELEASE_CONTRACTS_MARKER,
        label="release contracts",
    )
    validate_release_contracts(contracts)
    return contracts


def validate_runtime_manifest(manifest: dict[str, object]) -> None:
    if manifest.get("schema_version") != 2:
        raise RuntimeError("Unsupported sidecar runtime manifest schema")
    if manifest.get("frozen") is not True:
        raise RuntimeError("Release sidecar did not report a frozen runtime")
    expected_python = sidecar_python_version()
    if manifest.get("python_version") != expected_python:
        raise RuntimeError(
            "Release sidecar Python version differs from the production pin"
        )
    if manifest.get("build_python_version") != expected_python:
        raise RuntimeError("Release sidecar build provenance has the wrong Python version")
    if manifest.get("build_python_build") != sidecar_python_build():
        raise RuntimeError(
            "Release sidecar build provenance has the wrong "
            "python-build-standalone build"
        )
    if manifest.get("build_lock_file") != BUILD_LOCK.name:
        raise RuntimeError("Release sidecar build provenance has the wrong lock file")
    if manifest.get("build_lock_sha256") != _sha256(BUILD_LOCK):
        raise RuntimeError("Release sidecar build lock hash differs from the repository lock")
    packages = manifest.get("build_packages")
    if not isinstance(packages, dict) or any(
        not isinstance(packages.get(name), str) or not packages[name]
        for name in KEY_BUILD_PACKAGES
    ):
        raise RuntimeError("Release sidecar build provenance is missing package versions")
    revision = manifest.get("source_git_commit")
    if not isinstance(revision, str) or len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise RuntimeError("Release sidecar build provenance has no valid Git commit")
    if not isinstance(manifest.get("source_git_dirty"), bool):
        raise RuntimeError("Release sidecar build provenance has no worktree state")
    source_digest = manifest.get("engine_source_sha256")
    if not isinstance(source_digest, str) or len(source_digest) != 64 or any(
        character not in "0123456789abcdef" for character in source_digest
    ):
        raise RuntimeError("Release sidecar build provenance has no valid engine source hash")
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


def validate_current_source_provenance(manifest: dict[str, object]) -> None:
    """Bind a newly built Sidecar to the source tree that invoked the build."""

    if manifest.get("engine_source_sha256") != _source_tree_sha256(ENGINE_DIR):
        raise RuntimeError(
            "Release sidecar engine source hash differs from the current source tree"
        )


def validate_release_contracts(contracts: dict[str, object]) -> None:
    if contracts.get("schema_version") != 1:
        raise RuntimeError("Unsupported Sidecar release-contract schema")
    schema_list = contracts.get("schema_list_empty_arguments")
    if not isinstance(schema_list, dict) or schema_list != {
        "status": "allowed",
        "safe_args": {"limit": 20},
    }:
        raise RuntimeError(
            "Release blocked: final Sidecar rejects schema_list empty arguments "
            "instead of applying canonical defaults"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_artifact_manifest(
    binary: Path,
    runtime: dict[str, object],
    release_contracts: dict[str, object],
) -> Path:
    artifact = {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "target_triplet": get_target_triplet(),
        "sidecar_filename": binary.name,
        "sidecar_sha256": _sha256(binary),
        "minimum_sqlite_version": ".".join(str(part) for part in MINIMUM_SQLITE_VERSION),
        "target_sqlite_version": TARGET_SQLITE_VERSION,
        "runtime": runtime,
        "release_contracts": release_contracts,
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


def refresh_artifact_manifest_after_platform_signing() -> Path:
    """Rebind the manifest after an official platform signer mutates the executable."""

    try:
        existing = json.loads(RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Sidecar artifact manifest is unavailable for refresh") from error
    expected_name = "dbfox-engine.exe" if sys.platform == "win32" else "dbfox-engine"
    runtime = existing.get("runtime")
    release_contracts = existing.get("release_contracts")
    if (
        existing.get("schema_version") != ARTIFACT_MANIFEST_SCHEMA_VERSION
        or existing.get("sidecar_filename") != expected_name
        or not isinstance(runtime, dict)
        or not isinstance(release_contracts, dict)
    ):
        raise RuntimeError("Sidecar artifact manifest cannot be safely refreshed")
    binary = BINARIES_DIR / expected_name
    if not binary.is_file():
        raise RuntimeError("Signed Sidecar executable is unavailable for manifest refresh")
    signed_runtime = probe_sidecar_runtime(binary)
    validate_current_source_provenance(signed_runtime)
    signed_release_contracts = probe_sidecar_release_contracts(binary)
    if signed_runtime != runtime or signed_release_contracts != release_contracts:
        raise RuntimeError("Platform signing changed the probed Sidecar contract")
    return write_artifact_manifest(binary, signed_runtime, signed_release_contracts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DBFox engine sidecar")
    parser.add_argument(
        "--refresh-artifact-manifest",
        action="store_true",
        help="Recompute the Sidecar hash after official platform code signing",
    )
    parser.add_argument(
        "--system-dlc-signing-key",
        type=Path,
        default=(
            Path(os.environ["DBFOX_SYSTEM_DLC_SIGNING_KEY_PATH"])
            if os.environ.get("DBFOX_SYSTEM_DLC_SIGNING_KEY_PATH")
            else None
        ),
        help=(
            "PEM Ed25519 private key used only by the release builder; may also "
            "be supplied through DBFOX_SYSTEM_DLC_SIGNING_KEY_PATH"
        ),
    )
    args = parser.parse_args()

    if args.refresh_artifact_manifest:
        refresh_artifact_manifest_after_platform_signing()
        return

    print("=" * 55)
    print("DBFox Sidecar Builder")
    print("=" * 55)

    # Validate build prerequisites before producing any build output. A failed
    # package build must not leave a half-written sidecar behind.
    python_exe = _venv_python()
    print("\n[1/4] Sync locked build environment")
    sync_build_environment(python_exe)

    if args.system_dlc_signing_key is None:
        raise RuntimeError(
            "Frozen releases require --system-dlc-signing-key or "
            "DBFOX_SYSTEM_DLC_SIGNING_KEY_PATH"
        )
    system_dlc_manifest = build_system_dlc_release_bundle(
        python_exe,
        args.system_dlc_signing_key,
    )

    print("\n[2/4] PyInstaller build")
    binary = build_pyinstaller(python_exe, system_dlc_manifest)

    print("\n[3/4] Install to Electron resources")
    dest = install_sidecar(binary)

    print("\n[4/4] Probe final sidecar and enforce release contracts")
    try:
        runtime_manifest = probe_sidecar_runtime(dest)
        validate_current_source_provenance(runtime_manifest)
        release_contracts = probe_sidecar_release_contracts(dest)
        write_artifact_manifest(dest, runtime_manifest, release_contracts)
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
    print("  Next: cd desktop && npm run electron:package")
    print("=" * 55)


if __name__ == "__main__":
    main()
