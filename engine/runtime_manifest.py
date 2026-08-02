"""Self-reported runtime facts emitted by the final frozen sidecar."""

from __future__ import annotations

import _sqlite3
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Any

from engine import __version__


RUNTIME_MANIFEST_SCHEMA_VERSION = 1


def collect_runtime_manifest() -> dict[str, Any]:
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
    }
