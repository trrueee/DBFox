"""Self-reported runtime facts emitted by the final frozen sidecar."""

from __future__ import annotations

import _sqlite3
import json
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Any

from engine import __version__


RUNTIME_MANIFEST_SCHEMA_VERSION = 2
BUILD_PROVENANCE_FILENAME = "_build_provenance.json"


def _build_provenance() -> dict[str, Any]:
    path = Path(__file__).resolve().with_name(BUILD_PROVENANCE_FILENAME)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def collect_runtime_manifest() -> dict[str, Any]:
    provenance = _build_provenance()
    with sqlite3.connect(":memory:") as connection:
        source_id = str(connection.execute("SELECT sqlite_source_id()").fetchone()[0])
        compile_options = sorted(
            str(row[0]) for row in connection.execute("PRAGMA compile_options").fetchall()
        )
    return {
        "schema_version": RUNTIME_MANIFEST_SCHEMA_VERSION,
        "dbfox_version": __version__,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_version_info": list(sqlite3.sqlite_version_info),
        "sqlite_source_id": source_id,
        "sqlite_compile_options": compile_options,
        # PyInstaller one-file extraction paths are random for every process.
        # The module filename identifies the loaded extension without making the
        # signed build manifest depend on a transient _MEI directory.
        "sqlite_extension_module": Path(str(getattr(_sqlite3, "__file__", "built-in"))).name,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "build_python_version": provenance.get("python_version"),
        "build_lock_file": provenance.get("lock_file"),
        "build_lock_sha256": provenance.get("lock_sha256"),
        "build_packages": provenance.get("packages", {}),
    }
