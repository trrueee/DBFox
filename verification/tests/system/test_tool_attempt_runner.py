"""P6 shared ToolAttemptHandler and runner seam contracts."""

from __future__ import annotations

import threading
import time
import sys

from sqlalchemy.orm import sessionmaker

from engine.models import Project
from verification.support.metadata import create_migrated_metadata_engine
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
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPresentation,
)
from engine.tools.materialization import current_tool_contract_hash


class _Control:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = threading.Event()
        if cancelled:
            self.cancelled.set()
        self.deadline = time.monotonic() + 5

    def is_cancelled(self) -> bool:
        return self.cancelled.is_set()


class _DatabaseProbeInput(ToolInputModel):
    pass


class _DatabaseProbeOutput(ToolOutputModel):
    has_database: bool


class _DatabaseProbeTool(BaseTool[_DatabaseProbeInput, _DatabaseProbeOutput]):
    name = "test_database_probe"
    group = "test"
    description = "Records the database resource supplied to one attempt."
    input_model = _DatabaseProbeInput
    output_model = _DatabaseProbeOutput
    presentation = ToolPresentation(title="Database probe", category="manage")
    execution = ToolExecutionSpec(capabilities=("network",))

    def __init__(self) -> None:
        self.seen_database: object | None = None

    def run(self, _tool_input, context):
        self.seen_database = context.require_one("dbfox.data.database")
        return _DatabaseProbeOutput(has_database=True)


class _FileProbeInput(ToolInputModel):
    path: str


class _FileProbeOutput(ToolOutputModel):
    ok: bool = True


class _FileProbeTool(BaseTool[_FileProbeInput, _FileProbeOutput]):
    name = "file_read"
    group = "workspace"
    description = "Generic resource-bound runner probe."
    input_model = _FileProbeInput
    output_model = _FileProbeOutput
    presentation = ToolPresentation(title="File probe", category="explore")
    execution = ToolExecutionSpec(required_resource_kinds=("workspace",))

    def run(self, _input, _context):
        return _FileProbeOutput()


def _request(workspace, version="1", registry=None):
    del workspace
    scope = ResourceScopeRef(
        kind="workspace",
        id="project-1",
        version="root-v1",
    )
    contract_hash = (
        "sha256:99"
        if version == "99"
        else (
            current_tool_contract_hash(registry.require("file_read"))
            if registry is not None
            else "sha256:1"
        )
    )
    return ToolAttemptRequest(
        mode="execute",
        tool_name="file_read",
        frozen_tool_declared_version=version,
        frozen_tool_contract_hash=contract_hash,
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
    registry.register(_FileProbeTool())
    registry.freeze()
    resolver = CompositeResourceResolver()
    resolver.register("workspace", lambda _ref: root)
    handler = ToolAttemptHandler(registry=registry, resolver=resolver)

    result = handler.run(_request(None, registry=registry))
    assert result.status == "success"
    assert result.output == {"ok": True}


def test_handler_preserves_exact_in_process_database_resource_identity() -> None:
    tool = _DatabaseProbeTool()
    registry = ToolRegistry().register(tool).freeze()
    request = ToolAttemptRequest(
        mode="execute",
        tool_name=tool.name,
        frozen_tool_declared_version=tool.version,
        frozen_tool_contract_hash=current_tool_contract_hash(tool),
        invocation=ToolInvocationContext(
            session_id="session-1",
            run_id="run-1",
            turn_id="turn-1",
            invocation_id="invocation-1",
            idempotency_key="idem-1",
            scope_refs=(ResourceScopeRef(kind="dbfox.data.database", id="datasource-1", version=1),),
        ),
        authorized_input={},
        attempt_timeout_ms=10_000,
    )
    database = object()
    database_ref = request.invocation.scope_refs[0]
    result = ToolAttemptHandler(
        registry=registry,
        resolver=CompositeResourceResolver(),
    ).run_with_resources(request, {database_ref.canonical(): database})

    assert result.status == "success"
    assert tool.seen_database is database


def test_handler_rejects_stale_frozen_tool_version(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(_FileProbeTool())
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
    registry.register(_FileProbeTool())
    registry.freeze()
    resolver = CompositeResourceResolver()
    resolver.register("workspace", lambda _ref: root)
    runner = InProcessAttemptRunner(
        ToolAttemptHandler(registry=registry, resolver=resolver)
    )
    control = _Control(cancelled=True)
    result = runner.run(request=_request(None), control=control)
    assert result.status == "failed"
    assert result.error_code == "TOOL_CANCELLED"


def test_isolated_worker_does_not_rehydrate_retired_core_workspace(tmp_path, monkeypatch) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    registry.register(_FileProbeTool())
    registry.freeze()
    metadata_path = tmp_path / "worker-metadata.db"
    metadata_engine = create_migrated_metadata_engine(metadata_path)
    SessionLocal = sessionmaker(bind=metadata_engine)
    with SessionLocal() as db:
        db.add(Project(id="project-1", name="Worker Project"))
        db.commit()
    monkeypatch.setenv("DBFOX_DATABASE_URL", f"sqlite:///{metadata_path}")
    runner = IsolatedProcessAttemptRunner(default_isolated_worker_command())
    try:
        version = current_tool_contract_hash(registry.require("file_read"))
        request = _request(None, registry=registry)
        request = request.model_copy(
            update={
                "invocation": request.invocation.model_copy(
                    update={
                        "scope_refs": (
                            ResourceScopeRef(
                                kind="workspace",
                                id="project-1",
                                version="root-v1",
                            ),
                        ),
                    }
                ),
                "frozen_tool_contract_hash": version,
            }
        )
        result = runner.run(request=request, control=_Control())
        assert result.status == "failed"
        assert result.error_code == "TOOL_EXECUTION_FAILED"
        assert result.artifact_drafts == []
    finally:
        metadata_engine.dispose()


def test_isolated_runner_reports_missing_worker_as_unavailable(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(("definitely-missing-dbfox-worker",))
    result = runner.run(request=_request(None), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_EXECUTION_BACKEND_UNAVAILABLE"


def test_isolated_runner_rejects_malformed_worker_output(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(
        (sys.executable, "-c", "import sys; sys.stdout.write('garbage\\n')")
    )
    result = runner.run(request=_request(None), control=_Control())
    assert result.status == "failed"
    assert result.error_code == "TOOL_EXECUTION_INVALID_RESULT"


def test_isolated_runner_maps_worker_crash_to_unknown_outcome(tmp_path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_bytes(bytes([112, 114, 105, 110, 116, 40, 41, 10]))
    runner = IsolatedProcessAttemptRunner(
        (sys.executable, "-c", "import sys; sys.exit(3)")
    )
    result = runner.run(request=_request(None), control=_Control())
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
    result = runner.run(request=_request(None), control=_Control())
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
            request=_request(None),
            control=control,
        )
    finally:
        timer.cancel()
    assert result.status == "failed"
    assert result.error_code == "TOOL_CANCELLED"
