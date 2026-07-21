from __future__ import annotations

from pydantic import BaseModel

from engine.tools.materialization import ToolRecoveryPolicy, materialize_tools
from engine.tools.runtime.base import BaseTool, ToolExecutionSpec, ToolPolicy
from engine.tools.runtime.registry import ToolRegistry


class _Input(BaseModel):
    value: str


class _Output(BaseModel):
    value: str


class _ReadTool(BaseTool[_Input, _Output]):
    name = "schema.read"
    group = "schema"
    description = "Read schema"
    input_model = _Input
    output_model = _Output
    policy = ToolPolicy(side_effect="read")
    execution = ToolExecutionSpec(capabilities=("metadata_read",))


class _HiddenTool(BaseTool[_Input, _Output]):
    name = "internal.hidden"
    group = "internal"
    description = "Hidden"
    input_model = _Input
    output_model = _Output
    policy = ToolPolicy(visible_to_model=False)


def test_materialization_is_filtered_versioned_and_stable() -> None:
    registry = ToolRegistry().register(_HiddenTool()).register(_ReadTool())

    first = materialize_tools(registry, allowed_groups={"schema"}, execution_mode="user_requested_read")
    second = materialize_tools(registry, allowed_groups={"schema"}, execution_mode="user_requested_read")

    assert first.hash == second.hash
    assert [tool.name for tool in first.tools] == ["schema.read"]
    assert first.tools[0].recovery_policy is ToolRecoveryPolicy.RETRY_SAFE
    assert first.provider_schemas()[0]["function"]["parameters"]["properties"]["value"]["type"] == "string"
