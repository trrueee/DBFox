"""P8 Workspace file_write_patch contract and isolated transport tests."""

from __future__ import annotations

import hashlib
import threading
import time

from sqlalchemy.orm import sessionmaker

from engine.agent.artifact import validate_artifact_payload
from engine.models import Project
from engine.tests.support.metadata import create_migrated_metadata_engine
from engine.tools.builtin.registry import register_workspace_write_extension
from engine.tools.runtime import ToolRegistry, ToolRuntime
from engine.tools.runtime.attempt import (
    ResourceScopeRef,
    ToolAttemptRequest,
    ToolInvocationContext,
)
from engine.tools.runtime.attempt_runner import (
    IsolatedProcessAttemptRunner,
    default_isolated_worker_command,
)
from engine.tools.materialization import current_tool_contract_hash
from engine.workspace.read_service import WorkspaceReadService


def _write_registry():
    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    register_workspace_write_extension(registry)
    return registry.freeze()


def _control():
    class Control:
        def __init__(self) -> None:
            self.cancelled = threading.Event()
            self.deadline = time.monotonic() + 15

        def is_cancelled(self) -> bool:
            return self.cancelled.is_set()

    return Control()


def test_file_write_patch_creates_file_with_artifact(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    service = WorkspaceReadService(root)
    result = ToolRuntime(_write_registry()).invoke(
        tool_name="file_write_patch",
        raw_input={"path": "new.txt", "content": "hello\n"},
        request=None,
        idempotency_key="write-create-1",
        scope_refs=(
            ResourceScopeRef(
                kind="workspace",
                id="project-1",
                version="v1",
            ),
        ),
        resources={"workspace": service},
    )

    assert result.status == "success"
    assert (root / "new.txt").read_text(encoding="utf-8") == "hello\n"
    assert result.artifact_drafts[0].type == "dbfox.workspace.code_patch"


def test_file_write_patch_requires_current_sha_for_existing_file(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "existing.txt"
    target.write_text("old\n", encoding="utf-8")
    service = WorkspaceReadService(root)

    result = ToolRuntime(_write_registry()).invoke(
        tool_name="file_write_patch",
        raw_input={"path": "existing.txt", "content": "new\n"},
        request=None,
        idempotency_key="write-existing-1",
        scope_refs=(
            ResourceScopeRef(
                kind="workspace",
                id="project-1",
                version="v1",
            ),
        ),
        resources={"workspace": service},
    )
    assert result.status == "failed"
    assert result.error_code == "TOOL_INPUT_ERROR"
    assert target.read_text(encoding="utf-8") == "old\n"


def test_file_write_patch_updates_only_when_cas_matches(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "existing.txt"
    target.write_text("old\n", encoding="utf-8")
    old_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    service = WorkspaceReadService(root)

    result = ToolRuntime(_write_registry()).invoke(
        tool_name="file_write_patch",
        raw_input={
            "path": "existing.txt",
            "content": "new\n",
            "expected_sha256": old_sha,
        },
        request=None,
        idempotency_key="write-cas-1",
        scope_refs=(
            ResourceScopeRef(
                kind="workspace",
                id="project-1",
                version="v1",
            ),
        ),
        resources={"workspace": service},
    )
    assert result.status == "success"
    assert target.read_text(encoding="utf-8") == "new\n"


def test_file_write_patch_reconcile_uses_filesystem_state(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "reconcile.txt"
    target.write_bytes(b"done\n")
    service = WorkspaceReadService(root)
    registry = _write_registry()

    reconciled = ToolRuntime(registry).reconcile(
        tool_name="file_write_patch",
        raw_input={"path": "reconcile.txt", "content": "done\n"},
        request=None,
        idempotency_key="write-reconcile-1",
        scope_refs=(
            ResourceScopeRef(
                kind="workspace",
                id="project-1",
                version="v1",
            ),
        ),
        resources={"workspace": service},
    )
    assert reconciled.status == "success"


def test_code_patch_artifact_contract_is_registered() -> None:
    payload = validate_artifact_payload(
        "dbfox.workspace.code_patch",
        {
            "relativePath": "app.py",
            "oldSha256": None,
            "newSha256": "a" * 64,
            "sizeBytes": 10,
            "created": True,
        },
        schema_version=1,
    )
    assert payload["relativePath"] == "app.py"
    assert payload["created"] is True


def test_isolated_runner_rehydrates_canonical_workspace_for_file_write(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    registry = _write_registry()
    contract_hash = current_tool_contract_hash(registry.require("file_write_patch"))
    request = ToolAttemptRequest(
        mode="execute",
        tool_name="file_write_patch",
        frozen_tool_declared_version="1",
        frozen_tool_contract_hash=contract_hash,
        invocation=ToolInvocationContext(
            session_id="s",
            run_id="r",
            turn_id="t",
            invocation_id="i",
            idempotency_key="k",
            scope_refs=(
                ResourceScopeRef(
                    kind="workspace",
                    id="project-1",
                    version=hashlib.sha256(
                        str(root.resolve()).encode("utf-8")
                    ).hexdigest()[:16],
                ),
            ),
        ),
        authorized_input={"path": "created.txt", "content": "isolated\n"},
        attempt_timeout_ms=10_000,
    )
    metadata_path = tmp_path / "worker-metadata.db"
    metadata_engine = create_migrated_metadata_engine(metadata_path)
    SessionLocal = sessionmaker(bind=metadata_engine)
    with SessionLocal() as db:
        db.add(Project(id="project-1", name="Worker Project", workspace_root=str(root)))
        db.commit()
    monkeypatch.setenv("DBFOX_DATABASE_URL", f"sqlite:///{metadata_path}")
    runner = IsolatedProcessAttemptRunner(default_isolated_worker_command())
    try:
        result = runner.run(request=request, control=_control())

        assert result.status == "success"
        assert (root / "created.txt").read_text(encoding="utf-8") == "isolated\n"
        assert result.artifact_drafts[0].type == "dbfox.workspace.code_patch"
    finally:
        metadata_engine.dispose()
