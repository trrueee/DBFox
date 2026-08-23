from __future__ import annotations

import sqlite3
from pathlib import Path

import _sqlite3

from engine.runtime_manifest import collect_release_contracts, collect_runtime_manifest


def test_runtime_manifest_reports_loaded_sqlite_library() -> None:
    manifest = collect_runtime_manifest()

    assert manifest["schema_version"] == 2
    assert manifest["sqlite_version"] == sqlite3.sqlite_version
    assert manifest["sqlite_version_info"] == list(sqlite3.sqlite_version_info)
    assert len(manifest["sqlite_source_id"].split()) >= 3
    assert manifest["sqlite_compile_options"]
    assert manifest["sqlite_extension_module"] == Path(str(getattr(_sqlite3, "__file__", "built-in"))).name
    assert "/" not in manifest["sqlite_extension_module"]
    assert "\\" not in manifest["sqlite_extension_module"]
    assert manifest["python_version"]
    assert isinstance(manifest["frozen"], bool)
    assert manifest["build_python_version"] is None
    assert manifest["build_python_build"] is None
    assert manifest["build_lock_file"] is None
    assert manifest["build_lock_sha256"] is None
    assert manifest["build_packages"] == {}
    assert manifest["source_git_commit"] is None
    assert manifest["source_git_dirty"] is None
    assert manifest["engine_source_sha256"] is None


def test_release_contracts_apply_kernel_tool_canonical_defaults() -> None:
    assert collect_release_contracts() == {
        "schema_version": 1,
        "request_clarification_defaults": {
            "status": "allowed",
            "safe_args": {
                "question": "Select a target",
                "reason": "A target is required.",
                "options": [],
                "allow_free_text": True,
            },
        },
    }
