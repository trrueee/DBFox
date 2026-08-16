"""P6 shared ToolAttemptHandler and runner seam contracts."""

from __future__ import annotations

import threading
import time

from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ToolAttemptRequest,
    ToolInvocationContext,
)
from engine.tools.runtime.attempt_runner import (
    InProcessAttemptRunner,
    IsolatedProcessAttemptRunner,
)
from engine.tools.runtime.handler import ToolAttemptHandler
from engine.tools.runtime import ToolRegistry
from engine.tools.builtin.registry import register_workspace_extension
from engine.workspace.read_service import WorkspaceReadService


class _Control:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = threading.Event()
        if cancelled:
            self.cancelled.set()
        self.deadline = time.monotonic() + 5

    def is_cancelled(self) -> bool:
        return self.cancelled.is_set()


def _request(workspace, version="1"):
    scope = ResourceScopeRef(kind="workspace", id="project-1", version="root-v1")
    return ToolAttemptRequest(
        mode="execute",
        tool_name="file_read",
        frozen_tool_version=version,
        invocation=ToolInvocationContext(
            session_id="session-1",
            run_id="run-1",
            turn_id="turn-1",
            invocation_id="invocation-1",
            idempotency_key="idem-1",
            scope_refs=(scope,),
        ),
        authorized_input={"path": "src/main.py"},
        attempt_timeout_ms=1_000,
    )


def test_shared_handler_runs_a_workspace_attempt(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    registry = ToolRegistry()
    register_workspace_extension(registry)
    registry.freeze()
    resolver = CompositeResourceResolver()
    resolver.register("workspace", lambda ref: WorkspaceReadService(root))
    handler = ToolAttemptHandler(registry=registry, resolver=resolver)

    result = handler.run(_request(WorkspaceReadService(root)))
    assert result.status == "success"
    assert result.artifact_drafts[0].type == "dbfox.workspace.file_snapshot"


def test_handler_rejects_stale_frozen_tool_version(tmp_path) -> None:
    registry = ToolRegistry()
    register_workspace_extension(registry)
    registry.freeze()
    handler = ToolAttemptHandler(
        registry=registry,
        resolver=CompositeResourceResolver(),
    )
    result = handler.run(_request(None, version="99"))
    assert result.status == "failed"
    assert result.error_code == "TOOL_VERSION_CHANGED"


def test_in_process_runner_suppresses_late_success_after_cancel(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    registry = ToolRegistry()
    register_workspace_extension(registry)
    registry.freeze()
    resolver = CompositeResourceResolver()
    resolver.register("workspace", lambda ref: WorkspaceReadService(root))
    runner = InProcessAttemptRunner(
        ToolAttemptHandler(registry=registry, resolver=resolver)
    )
    control = _Control(cancelled=True)
    result = runner.run(request=_request(None), control=control)
    assert result.status == "failed"
    assert result.error_code == "TOOL_CANCELLED"


def test_isolated_runner_skeleton_returns_unavailable_without_claiming_sandbox() -> None:
    runner = IsolatedProcessAttemptRunner(("python", "-m", "dbfox_worker"))
    result = runner.run(request=_request(None), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_EXECUTION_BACKEND_UNAVAILABLE"
