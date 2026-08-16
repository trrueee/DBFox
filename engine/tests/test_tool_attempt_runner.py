"""P6 shared ToolAttemptHandler and runner seam contracts."""

from __future__ import annotations

import threading
import time
import sys

from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ToolAttemptRequest,
    ToolInvocationContext,
)
from engine.tools.runtime.attempt_runner import (
    InProcessAttemptRunner,
    IsolatedProcessAttemptRunner,
    default_isolated_worker_command,
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
    location = (
        str(workspace.root)
        if isinstance(workspace, WorkspaceReadService)
        else None
    )
    scope = ResourceScopeRef(
        kind="workspace",
        id="project-1",
        version="root-v1",
        location=location,
    )
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
        attempt_timeout_ms=10_000,
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


def test_isolated_runner_executes_worker_attempt(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(default_isolated_worker_command())
    result = runner.run(
        request=_request(WorkspaceReadService(root)),
        control=_Control(),
    )
    assert result.status == "success"
    assert result.artifact_drafts[0].type == "dbfox.workspace.file_snapshot"


def test_isolated_runner_reports_missing_worker_as_unavailable(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(("definitely-missing-dbfox-worker",))
    result = runner.run(request=_request(WorkspaceReadService(root)), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_EXECUTION_BACKEND_UNAVAILABLE"


def test_isolated_runner_rejects_malformed_worker_output(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(
        (sys.executable, "-c", "import sys; sys.stdout.write('garbage\\n')")
    )
    result = runner.run(request=_request(WorkspaceReadService(root)), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_EXECUTION_INVALID_RESULT"


def test_isolated_runner_maps_worker_crash_to_unknown_outcome(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(
        (sys.executable, "-c", "import sys; sys.exit(3)")
    )
    result = runner.run(request=_request(WorkspaceReadService(root)), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_OUTCOME_UNKNOWN"


def test_isolated_runner_bounds_stdout(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(
        (sys.executable, "-c", "import sys; sys.stdout.write('x' * 100000)"),
        max_stdout_bytes=64,
    )
    result = runner.run(request=_request(WorkspaceReadService(root)), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_EXECUTION_OUTPUT_TOO_LARGE"


def test_isolated_runner_cancels_running_worker(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(
        (sys.executable, "-c", "import time; time.sleep(5)")
    )
    control = _Control()
    timer = threading.Timer(0.1, control.cancelled.set)
    timer.start()
    try:
        result = runner.run(
            request=_request(WorkspaceReadService(root)),
            control=control,
        )
    finally:
        timer.cancel()
    assert result.status == "failed"
    assert result.error_code == "TOOL_CANCELLED"
