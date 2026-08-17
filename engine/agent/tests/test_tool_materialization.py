from __future__ import annotations

import pytest

from engine.tools.materialization import (
    ToolVersionMismatch,
    materialize_tools,
    require_current_tool,
)
from engine.tools.builtin import register_dbfox_tools
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRecoveryPolicy,
)
from engine.tools.runtime.registry import ToolRegistry


class _Input(ToolInputModel):
    value: str
    note: str | None = None


class _Output(ToolOutputModel):
    value: str


class _ReadTool(BaseTool[_Input, _Output]):
    name = "schema_read"
    group = "schema"
    description = "Read schema"
    input_model = _Input
    output_model = _Output
    presentation = ToolPresentation(title="Read schema", category="explore")
    policy = ToolPolicy()
    execution = ToolExecutionSpec(
        recovery=ToolRecoveryPolicy.RETRY_SAFE,
        capabilities=("metadata_read",),
    )


class _HiddenTool(BaseTool[_Input, _Output]):
    name = "internal_hidden"
    group = "internal"
    description = "Hidden"
    input_model = _Input
    output_model = _Output
    presentation = ToolPresentation(title="Internal tool", category="manage", visibility="developer")
    policy = ToolPolicy(visible_to_model=False)


def test_materialization_is_filtered_versioned_and_stable() -> None:
    registry = ToolRegistry().register(_HiddenTool()).register(_ReadTool())

    first = materialize_tools(registry, allowed_groups={"schema"}, execution_mode="user_requested_read")
    second = materialize_tools(registry, allowed_groups={"schema"}, execution_mode="user_requested_read")

    assert first.hash == second.hash
    assert [tool.name for tool in first.tools] == ["schema_read"]
    assert first.tools[0].recovery_policy is ToolRecoveryPolicy.RETRY_SAFE
    assert first.provider_schemas()[0]["parameters"]["properties"]["value"]["type"] == "string"
    assert first.provider_schemas()[0]["parameters"]["additionalProperties"] is False
    assert first.provider_schemas()[0]["parameters"]["required"] == ["value", "note"]
    assert first.provider_schemas()[0]["strict"] is True


def test_materialization_can_narrow_a_group_to_an_explicit_completion_set() -> None:
    registry = register_dbfox_tools()

    materialization = materialize_tools(
        registry,
        allowed_groups={"control", "result"},
        allowed_names={"update_plan", "result_inspect", "result_profile"},
        execution_mode="agent_autonomous_read",
    )

    assert {tool.name for tool in materialization.tools} == {
        "update_plan",
        "result_inspect",
        "result_profile",
    }


def test_tools_are_not_retry_safe_without_an_explicit_recovery_contract() -> None:
    class _DefaultTool(BaseTool[_Input, _Output]):
        name = "default_execution"
        group = "internal"
        description = "Default execution contract"
        input_model = _Input
        output_model = _Output
        presentation = ToolPresentation(title="Default", category="manage")

    materialization = materialize_tools(
        ToolRegistry().register(_DefaultTool()),
        allowed_groups={"internal"},
        execution_mode="user_requested_read",
    )
    assert materialization.tools[0].recovery_policy is ToolRecoveryPolicy.NEVER_RETRY


def test_reconcile_recovery_requires_a_tool_reconciler() -> None:
    with pytest.raises(TypeError, match="must implement reconcile"):
        class _InvalidReconcileTool(BaseTool[_Input, _Output]):
            name = "invalid_reconcile"
            group = "internal"
            description = "Missing reconciliation implementation"
            input_model = _Input
            output_model = _Output
            presentation = ToolPresentation(title="Invalid", category="manage")
            execution = ToolExecutionSpec(recovery=ToolRecoveryPolicy.RECONCILE)


def test_pending_call_cannot_cross_a_tool_version_boundary() -> None:
    materialization = materialize_tools(
        ToolRegistry().register(_ReadTool()),
        allowed_groups={"schema"},
        execution_mode="user_requested_read",
    )
    frozen_contract = materialization.require("schema_read").contract_hash

    class _ReadToolV2(_ReadTool):
        version = "2"

    current_registry = ToolRegistry().register(_ReadToolV2())
    with pytest.raises(ToolVersionMismatch):
        require_current_tool(
            current_registry,
            materialization,
            name="schema_read",
            contract_hash=frozen_contract,
        )

    with pytest.raises(ToolVersionMismatch):
        require_current_tool(
            ToolRegistry(),
            materialization,
            name="schema_read",
            contract_hash=frozen_contract,
        )


def test_pending_call_cannot_cross_a_contract_change_with_same_declared_version() -> None:
    materialization = materialize_tools(
        ToolRegistry().register(_ReadTool()),
        allowed_groups={"schema"},
        execution_mode="user_requested_read",
    )
    frozen_contract = materialization.require("schema_read").contract_hash

    class _ChangedInput(ToolInputModel):
        value: int
        note: str | None = None

    class _ReadToolChangedContract(_ReadTool):
        input_model = _ChangedInput

    with pytest.raises(ToolVersionMismatch):
        require_current_tool(
            ToolRegistry().register(_ReadToolChangedContract()),
            materialization,
            name="schema_read",
            contract_hash=frozen_contract,
        )


def test_pending_call_cannot_cross_a_policy_change_with_same_declared_version() -> None:
    materialization = materialize_tools(
        ToolRegistry().register(_ReadTool()),
        allowed_groups={"schema"},
        execution_mode="user_requested_read",
    )
    frozen_contract = materialization.require("schema_read").contract_hash

    class _ReadToolChangedPolicy(_ReadTool):
        policy = ToolPolicy(requires_approval=True)

    with pytest.raises(ToolVersionMismatch):
        require_current_tool(
            ToolRegistry().register(_ReadToolChangedPolicy()),
            materialization,
            name="schema_read",
            contract_hash=frozen_contract,
        )


def test_dbfox_tools_publish_openai_strict_schemas() -> None:
    materialization = materialize_tools(
        register_dbfox_tools(),
        execution_mode="user_requested_read",
    )

    def assert_strict_objects(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" or "properties" in value:
                properties = set((value.get("properties") or {}).keys())
                assert value.get("additionalProperties") is False
                assert set(value.get("required") or []) == properties
            for child in value.values():
                assert_strict_objects(child)
        elif isinstance(value, list):
            for child in value:
                assert_strict_objects(child)

    provider_schemas = materialization.provider_schemas()
    assert {tool.name for tool in materialization.tools} == {
        schema["name"] for schema in provider_schemas
    }
    for schema in provider_schemas:
        assert schema["strict"] is True
        assert_strict_objects(schema["parameters"])

    search = materialization.require("schema_search")
    search_properties = search.input_schema["properties"]
    assert search_properties["queries"]["maxItems"] == 4
    assert search_properties["queries"]["items"]["maxLength"] == 512
    assert search_properties["limit_per_query"]["minimum"] == 1
    assert search_properties["limit_per_query"]["maximum"] == 20

    update_plan = materialization.require("update_plan")
    assert "complete current objective and complete steps array" in (
        update_plan.description
    )
    assert {"objective", "steps"} <= set(update_plan.input_schema["required"])


def test_dbfox_tool_capabilities_are_the_single_resource_access_contract() -> None:
    registry = register_dbfox_tools()

    assert registry.require("catalog_overview").execution.capabilities == (
        "metadata_read",
    )
    assert registry.require("catalog_refresh").execution.capabilities == (
        "metadata_read",
        "metadata_write",
        "database_read",
    )
    assert registry.require("schema_inspect").execution.capabilities == ("metadata_read",)
    assert registry.require("conversation_search").execution.capabilities == ("metadata_read",)
    assert registry.require("conversation_read").execution.capabilities == ("metadata_read",)
    assert registry.require("data_preview").execution.capabilities == (
        "metadata_read",
        "database_read",
    )
    assert registry.require("sql_execute_readonly").execution.capabilities == (
        "metadata_read",
        "database_read",
    )
    assert registry.require("update_plan").execution.capabilities == ()
