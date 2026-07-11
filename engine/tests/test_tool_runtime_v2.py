from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from engine.agent_core.types import ToolObservation
from engine.tools.runtime.base import (
    ArtifactSpec,
    BaseTool,
    ToolExecutionSpec,
    ToolPolicy,
    ToolStateSpec,
)
from engine.tools.runtime.context import ToolRunContext


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


def test_base_tool_exposes_typed_spec():
    tool = EchoTool()

    assert tool.spec.name == "test.echo"
    assert tool.spec.group == "test"
    assert tool.spec.input_model is EchoInput
    assert tool.spec.output_model is EchoOutput
    assert tool.spec.state.consumes == ("allowed",)


def test_registry_registers_base_tools_and_rejects_duplicates():
    from engine.tools.runtime.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(EchoTool())

    assert registry.require("test.echo").name == "test.echo"

    try:
        registry.register(EchoTool())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration should fail")


def test_manifest_exports_model_safe_alias():
    from engine.tools.runtime.manifest import build_langchain_tools
    from engine.tools.runtime.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(EchoTool())

    tools = build_langchain_tools(registry, allowed_groups=["test"])

    assert [tool.name for tool in tools] == ["test_echo"]


def test_runtime_projects_only_declared_state_keys():
    from engine.tools.runtime.registry import ToolRegistry
    from engine.tools.runtime.runtime import ToolRuntime

    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = ToolRuntime(registry)

    observation = runtime.invoke(
        tool_name="test.echo",
        raw_input={"value": "hello"},
        state={"allowed": 1, "secret": 2},
        request=None,
        db=None,
    )

    assert observation.status == "success"
    assert observation.output == {"value": "hello", "seen": {"allowed": 1}}


def test_runtime_reports_validation_failure_as_failed_observation():
    from engine.tools.runtime.registry import ToolRegistry
    from engine.tools.runtime.runtime import ToolRuntime

    registry = ToolRegistry()
    registry.register(EchoTool())
    runtime = ToolRuntime(registry)

    observation = runtime.invoke(
        tool_name="test.echo",
        raw_input={},
        state={},
        request=None,
        db=None,
    )

    assert observation.status == "failed"
    assert "Input contract failed" in (observation.error or "")


def test_state_reducer_clears_execute_readonly_errors():
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    obs = ToolObservation(
        name="sql.execute_readonly",
        status="success",
        output={"status": "success", "returned_rows": 1, "safe_sql": "SELECT 1"},
        latency_ms=1,
    )

    update = apply_tool_observation_to_state(
        state={"error": "old"},
        tool_name="sql.execute_readonly",
        observation=obs,
    )

    assert update["error"] is None
    assert update["execution"]["success"] is True
    assert update["sql"] == "SELECT 1"


def test_builtin_registry_loads_base_tools_without_yaml():
    from engine.tools.dbfox_tools import register_dbfox_tools

    registry = register_dbfox_tools()
    names = {tool.name for tool in registry.list_tools()}

    assert "db.query" not in names
    assert "sql.validate" in names
    assert "sql.execute_readonly" in names
    assert "chart.suggest" in names
    assert "answer.synthesize" not in names
    assert "analyze_data" not in names


def test_model_visible_sql_lifecycle_excludes_internal_db_query():
    from engine.tools.dbfox_tools import register_dbfox_tools
    from engine.tools.runtime.manifest import build_langchain_tools

    tools = build_langchain_tools(register_dbfox_tools(), allowed_groups=["db", "sql"])
    names = {tool.name for tool in tools}

    assert "db_query" not in names
    assert "query_database" not in names
    assert "sql_validate" in names
    assert "sql_execute_readonly" in names


def test_execute_readonly_model_schema_does_not_accept_sql_text():
    from engine.tools.dbfox_tools import SqlExecuteReadonlyInput

    assert "sql" not in SqlExecuteReadonlyInput.model_fields
    assert "question" in SqlExecuteReadonlyInput.model_fields


def test_retired_db_query_tool_has_no_registry_alias_or_prompt_entry():
    from engine.agent.model.system_prompt import SYSTEM_PROMPT
    from engine.tools.dbfox_tools import register_dbfox_tools
    from engine.tools.runtime.aliases import ALIAS_TO_INTERNAL, STEP_NAME_MAP, STEP_NAME_TO_INTERNAL

    registry = register_dbfox_tools()
    assert registry.get("db.query") is None

    assert "db_query" not in ALIAS_TO_INTERNAL
    assert "db.query" not in STEP_NAME_MAP
    assert "query_database" not in STEP_NAME_TO_INTERNAL
    assert "db.query" not in SYSTEM_PROMPT
    assert "query_database" not in SYSTEM_PROMPT
    assert "sql.validate" in SYSTEM_PROMPT
    assert "sql.execute_readonly" in SYSTEM_PROMPT


def test_legacy_memory_tools_are_not_registered():
    from engine.tools.dbfox_tools import register_dbfox_tools
    from engine.tools.runtime.manifest import build_langchain_tools

    registry = register_dbfox_tools()
    names = {tool.name for tool in registry.list_tools()}

    for name in ["memory.search", "memory.write", "memory.delete", "memory.summarize_session"]:
        assert name not in names

    assert build_langchain_tools(registry, allowed_groups=["memory"]) == []


def test_agent_runtime_does_not_expose_semantic_memory_write_tool():
    from engine.tools.dbfox_tools import register_dbfox_tools
    from engine.tools.runtime.manifest import build_langchain_tools

    registry = register_dbfox_tools()
    names = {tool.name for tool in registry.list_tools()}

    assert "db.remember" not in names
    tools = build_langchain_tools(registry, allowed_groups=["db"])
    assert "db_remember" not in {tool.name for tool in tools}


def test_runtime_failure_observation_never_contains_exception_text(monkeypatch, caplog):
    from engine.tools.runtime.registry import ToolRegistry
    from engine.tools.runtime.runtime import ToolRuntime

    sentinel = "tool-runtime-secret-sentinel"

    class FailingTool(BaseTool[EchoInput, EchoOutput]):
        name = "test.failing"
        group = "test"
        description = "Always fails."
        input_model = EchoInput
        output_model = EchoOutput
        policy = ToolPolicy()
        execution = ToolExecutionSpec()
        state = ToolStateSpec()
        artifacts = ArtifactSpec()

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> EchoOutput:
            raise RuntimeError(f"provider authorization={sentinel}")

    registry = ToolRegistry()
    registry.register(FailingTool())

    capture_logger = logging.Logger("test.tool_runtime_boundary")
    capture_logger.setLevel(logging.ERROR)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr("engine.tools.runtime.runtime.logger", capture_logger)
            observation = ToolRuntime(registry).invoke(
                tool_name="test.failing",
                raw_input={"value": "normal-input"},
                state={},
                request=None,
                db=None,
            )
    finally:
        capture_logger.removeHandler(caplog.handler)

    assert observation.status == "failed"
    assert observation.error == "Tool execution failed."
    assert observation.output == {
        "status": "failed",
        "error_code": "TOOL_EXECUTION_FAILED",
        "error_type": "RuntimeError",
    }
    assert sentinel not in observation.model_dump_json()
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "tool_runtime_tool_execution_failed" in caplog.text


def test_runtime_failure_observation_is_safe_in_real_checkpoint_and_event_storage(
    db_session,
    test_datasource,
):
    from engine.agent_core.event_store import SQLiteAgentEventStore
    from engine.agent_core.types import AgentRunRequest, AgentRuntimeEvent
    from engine.models import AgentCheckpoint, AgentRuntimeEventRecord
    from engine.tools.runtime.registry import ToolRegistry
    from engine.tools.runtime.runtime import ToolRuntime

    sentinel = "tool-checkpoint-secret-sentinel"

    class FailingTool(BaseTool[EchoInput, EchoOutput]):
        name = "test.checkpoint_failing"
        group = "test"
        description = "Always fails for persistence coverage."
        input_model = EchoInput
        output_model = EchoOutput
        policy = ToolPolicy()
        execution = ToolExecutionSpec()
        state = ToolStateSpec()
        artifacts = ArtifactSpec()

        def run(self, _tool_input: EchoInput, _context: ToolRunContext) -> EchoOutput:
            raise RuntimeError(f"provider authorization={sentinel}")

    registry = ToolRegistry()
    registry.register(FailingTool())
    observation = ToolRuntime(registry).invoke(
        tool_name="test.checkpoint_failing",
        raw_input={"value": "normal-input"},
        state={},
        request=None,
        db=None,
    )

    store = SQLiteAgentEventStore(db_session)
    request = AgentRunRequest(
        datasource_id=test_datasource.id,
        question="exercise tool failure persistence",
    )
    store.start_run(request, run_id="run-tool-boundary", session_id="session-tool-boundary")
    checkpoint = store.save_checkpoint(
        run_id="run-tool-boundary",
        session_id="session-tool-boundary",
        status="running",
        current_step_name="tools",
        next_step_name="observe",
        plan=None,
        state={"last_tool_results": [observation.model_dump(mode="json")]},
        completed_steps=[],
        pending_steps=[],
        artifacts=[],
    )
    store.append_event(
        "session-tool-boundary",
        AgentRuntimeEvent(
            event_id="event-tool-boundary",
            run_id="run-tool-boundary",
            session_id="session-tool-boundary",
            sequence=1,
            created_at_ms=1,
            type="agent.step.completed",
            step={
                "name": "tools",
                "tool_name": observation.name,
                "error": observation.error,
                "observation": observation.model_dump(mode="json"),
            },
        ),
    )
    db_session.commit()

    saved_checkpoint = db_session.get(AgentCheckpoint, checkpoint.id)
    saved_event = db_session.get(AgentRuntimeEventRecord, "event-tool-boundary")
    assert saved_checkpoint is not None
    assert saved_event is not None
    persisted = "\n".join(
        [
            saved_checkpoint.state_json,
            saved_checkpoint.completed_steps_json,
            saved_checkpoint.pending_steps_json,
            saved_event.event_json,
        ]
    )
    assert sentinel not in observation.model_dump_json()
    assert sentinel not in persisted
    assert "TOOL_EXECUTION_FAILED" in persisted


def test_db_tool_execution_failure_never_contains_exception_text(monkeypatch, caplog):
    from engine.tools.db._common import _execution_failed

    sentinel = "db-tool-observation-secret-sentinel"

    capture_logger = logging.Logger("test.db_tool_boundary")
    capture_logger.setLevel(logging.WARNING)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr("engine.tools.db._common.logger", capture_logger)
            observation = _execution_failed(
                "db.inspect",
                {"target": "orders"},
                RuntimeError(f"database password={sentinel}"),
                time.perf_counter(),
            )
    finally:
        capture_logger.removeHandler(caplog.handler)

    assert observation.status == "failed"
    assert observation.error == "Tool execution failed."
    assert observation.output == {
        "status": "failed",
        "error_code": "TOOL_EXECUTION_FAILED",
        "error_type": "RuntimeError",
    }
    assert sentinel not in observation.model_dump_json()
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "db_tool_execution" in caplog.text
