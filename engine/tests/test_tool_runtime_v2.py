from __future__ import annotations

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


def test_state_reducer_applies_result_profile():
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    obs = ToolObservation(
        name="result.profile",
        status="success",
        output={"row_count": 3},
        latency_ms=1,
    )

    update = apply_tool_observation_to_state(
        state={},
        tool_name="result.profile",
        observation=obs,
    )

    assert update["result_profile"] == {"row_count": 3}
    assert update["trace_events"][0]["payload"]["tool_name"] == "result.profile"


def test_state_reducer_clears_db_query_errors():
    from engine.tools.runtime.state_reducer import apply_tool_observation_to_state

    obs = ToolObservation(
        name="db.query",
        status="success",
        output={"status": "success", "returned_rows": 1, "safe_sql": "SELECT 1"},
        latency_ms=1,
    )

    update = apply_tool_observation_to_state(
        state={"error": "old"},
        tool_name="db.query",
        observation=obs,
    )

    assert update["error"] is None
    assert update["execution"]["success"] is True
    assert update["sql"] == "SELECT 1"


def test_builtin_registry_loads_base_tools_without_yaml():
    from engine.tools.dbfox_tools import register_dbfox_tools

    registry = register_dbfox_tools()
    names = {tool.name for tool in registry.list_tools()}

    assert "db.query" in names
    assert "result.profile" in names
    assert "chart.suggest" in names
    assert "answer.synthesize" in names
    assert "analyze_data" not in names


def test_wrapped_memory_tools_consume_identity_state():
    from engine.tools.dbfox_tools import register_dbfox_tools

    registry = register_dbfox_tools()
    required = {"datasource_id", "user_id", "project_id", "thread_id", "session_id"}

    for name in ["memory.search", "memory.write", "memory.delete", "memory.summarize_session"]:
        consumes = set(registry.require(name).state.consumes)
        assert required <= consumes


def test_semantic_resolve_consumes_workspace_context():
    from engine.tools.dbfox_tools import register_dbfox_tools

    registry = register_dbfox_tools()
    consumes = set(registry.require("semantic.resolve").state.consumes)

    assert {"datasource_id", "question", "workspace_context"} <= consumes
