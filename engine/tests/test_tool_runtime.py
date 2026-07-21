from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from engine.tools.runtime.base import ArtifactSpec, BaseTool, ToolExecutionSpec, ToolPolicy, ToolStateSpec
from engine.tools.runtime.context import ToolRunContext
from engine.tools.runtime.executor import ToolExecutor
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.result import ToolResult
from engine.tools.runtime.runtime import ToolRuntime


class EchoInput(BaseModel):
    value: str


class EchoOutput(BaseModel):
    value: str
    seen: dict[str, Any]


class EchoTool(BaseTool[EchoInput, EchoOutput]):
    name = "test.echo"
    group = "test"
    description = "Echo a value."
    input_model = EchoInput
    output_model = EchoOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("allowed",), produces=("echo",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EchoInput, context: ToolRunContext) -> EchoOutput:
        return EchoOutput(value=tool_input.value, seen=dict(context.state))


def test_registry_and_provider_neutral_tool_spec():
    registry = ToolRegistry()
    registry.register(EchoTool())
    spec = registry.require("test.echo").spec
    assert spec.input_model is EchoInput
    assert spec.state.consumes == ("allowed",)
    assert "langchain" not in type(registry).__module__


def test_registry_denies_privileged_capabilities_without_an_isolated_backend():
    class ProcessTool(EchoTool):
        name = "test.process"
        execution = ToolExecutionSpec(capabilities=("subprocess",))

    with pytest.raises(ValueError, match="require an isolated process"):
        ToolRegistry().register(ProcessTool())


def test_registry_requires_a_declared_read_capability():
    class UndeclaredReadTool(EchoTool):
        name = "test.undeclared_read"
        policy = ToolPolicy(side_effect="read")

    with pytest.raises(ValueError, match="must declare its read capability"):
        ToolRegistry().register(UndeclaredReadTool())


def test_registry_rejects_an_unavailable_execution_backend():
    class IsolatedTool(EchoTool):
        name = "test.isolated"
        execution = ToolExecutionSpec(
            backend="isolated_process",
            capabilities=("subprocess",),
        )

    with pytest.raises(ValueError, match="unavailable execution backend"):
        ToolRegistry().register(IsolatedTool())


def test_runtime_projects_only_declared_state_keys():
    registry = ToolRegistry()
    registry.register(EchoTool())
    result = ToolRuntime(registry).invoke(
        tool_name="test.echo", raw_input={"value": "hello"},
        state={"allowed": 1, "secret": 2}, request=None, db=None,
    )
    assert result == ToolResult(
        name="test.echo", status="success", input={"value": "hello"},
        output={"value": "hello", "seen": {"allowed": 1}}, error=None,
        latency_ms=result.latency_ms,
    )


def test_runtime_validation_and_execution_failures_are_safe(monkeypatch, caplog):
    class FailingTool(EchoTool):
        name = "test.failing"

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> EchoOutput:
            raise RuntimeError("password=secret-sentinel")

    registry = ToolRegistry()
    registry.register(FailingTool())
    logger = logging.Logger("test.tool-runtime")
    logger.addHandler(caplog.handler)
    with monkeypatch.context() as patch:
        patch.setattr("engine.tools.runtime.runtime.logger", logger)
        invalid = ToolRuntime(registry).invoke(
            tool_name="test.failing", raw_input={}, state={}, request=None, db=None,
        )
        failed = ToolRuntime(registry).invoke(
            tool_name="test.failing", raw_input={"value": "x"}, state={}, request=None, db=None,
        )
    assert invalid.status == "failed"
    assert "Input contract failed" in (invalid.error or "")
    assert failed.error == "Tool execution failed."
    assert "secret-sentinel" not in failed.model_dump_json()
    assert "secret-sentinel" not in caplog.text


def test_product_registry_contains_the_analysis_toolset():
    from engine.tools.dbfox_tools import register_dbfox_tools

    names = {tool.name for tool in register_dbfox_tools().list_tools()}
    assert {"db.observe", "db.search", "db.inspect", "db.preview", "sql.validate", "sql.execute_readonly", "artifact.inspect", "chart.suggest", "question.request", "plan.update"} <= names
    assert "db.query" not in names
    assert not any(name.startswith("memory.") for name in names)


def test_artifact_inspect_returns_only_a_transient_gateway_page(monkeypatch):
    from engine.sql.result_view.models import ResultPage, VerifiedResultSource
    from engine.tools.dbfox_tools import register_dbfox_tools

    db = SimpleNamespace(get=lambda _model, _id: SimpleNamespace(session_id="session-1"))
    monkeypatch.setattr(
        "engine.tools.dbfox_tools.ResultViewService.load_verified_source",
        lambda _self, _ref: VerifiedResultSource(
            datasource_id="ds-1", source_sql_artifact_id="sql-1", safe_sql="SELECT 1 AS total",
            dialect="sqlite", columns=[], fingerprint="query-1", datasource_generation=1,
        ),
    )
    monkeypatch.setattr(
        "engine.tools.dbfox_tools.ResultViewService.page",
        lambda _self, _query: ResultPage(
            columns=["total"], rows=[{"total": 1}], page=1, page_size=50,
            row_count=1, has_next_page=False, latency_ms=2,
            consistency="live_reexecution", original_executed_at="2026-07-20T00:00:00Z",
            view_executed_at="2026-07-20T00:00:01Z", view_execution_id="view-1",
            datasource_generation=1, query_fingerprint="query-1",
        ),
    )

    result = ToolRuntime(register_dbfox_tools()).invoke(
        tool_name="artifact.inspect",
        raw_input={"artifact_id": "artifact-result-1"},
        state={}, request=SimpleNamespace(session_id="session-1"), db=db,
    )

    assert result.status == "success"
    assert result.output["rows"] == [{"total": 1}]
    assert result.output["artifact_id"] == "artifact-result-1"
    assert result.output["queryFingerprint"] == "query-1"


def test_state_reducer_consumes_provider_neutral_results():
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    result = ToolResult(
        name="sql.execute_readonly", status="success",
        output={"status": "success", "returned_rows": 1, "safe_sql": "SELECT 1"},
        latency_ms=1,
    )
    update = apply_tool_observation_to_state(
        state={"error": "old"}, tool_name=result.name, observation=result,
    )
    assert update["error"] is None
    assert update["execution"]["success"] is True


def test_tool_executor_retries_only_declared_idempotent_operations():
    class RetryTool(EchoTool):
        name = "test.retry"
        execution = ToolExecutionSpec(idempotent=True, retryable=True, max_retries=2)

    attempts: list[int] = []

    def operation(_control):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return ToolResult(
                name="test.retry", status="failed", error="temporary",
                error_code="TOOL_EXECUTION_FAILED", latency_ms=1,
            )
        return ToolResult(name="test.retry", status="success", output={"ok": True}, latency_ms=1)

    result = ToolExecutor(max_workers=1).execute(
        tool=RetryTool(), scope_key="run-1", operation=operation,
    )

    assert result.status == "success"
    assert result.attempts == 3
    assert attempts == [1, 2, 3]


def test_tool_executor_timeout_signals_the_leaf_and_never_returns_late_success():
    cancelled = False

    def operation(control):
        while not control.is_cancelled():
            time.sleep(0.005)
        return ToolResult(name="test.echo", status="success", output={"late": True}, latency_ms=1)

    def cancel_action():
        nonlocal cancelled
        cancelled = True

    result = ToolExecutor(max_workers=1, poll_interval_seconds=0.005).execute(
        tool=EchoTool(), scope_key="run-timeout", operation=operation,
        cancel_action=cancel_action, timeout_seconds=0.03,
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_TIMEOUT"
    assert cancelled is True


def test_tool_executor_enforces_declared_output_bytes():
    class BoundedTool(EchoTool):
        name = "test.bounded"
        execution = ToolExecutionSpec(max_output_bytes=1_024)

    result = ToolExecutor(max_workers=1).execute(
        tool=BoundedTool(),
        scope_key="run-output",
        operation=lambda _control: ToolResult(
            name="test.bounded", status="success", output={"value": "x" * 2_000}, latency_ms=1,
        ),
    )

    assert result.status == "failed"
    assert result.error_code == "TOOL_OUTPUT_TOO_LARGE"
