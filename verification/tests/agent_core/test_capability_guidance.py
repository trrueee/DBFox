from __future__ import annotations

from engine.agent.guidance import (
    CapabilityGuidanceContribution,
    CapabilityGuidanceSpec,
    materialize_capability_guidance,
)
from engine.tools.materialization import materialize_tools
from engine.tools.runtime.base import (
    BaseTool,
    ToolInputModel,
    ToolOutputModel,
    ToolPresentation,
)
from engine.tools.runtime.registry import ToolKey, ToolRegistry


class _Input(ToolInputModel):
    value: str


class _Output(ToolOutputModel):
    value: str


class _MusicTool(BaseTool[_Input, _Output]):
    name = "compose"
    group = "music"
    description = "Compose a fixture"
    input_model = _Input
    output_model = _Output
    presentation = ToolPresentation(title="Compose", category="manage")


def _guidance() -> CapabilityGuidanceContribution:
    return CapabilityGuidanceContribution(
        owner_id="dbfox.music",
        package_digest="sha256:fixture",
        spec=CapabilityGuidanceSpec(
            id="composition",
            version="1",
            instructions="Preserve explicit musical constraints.",
            applies_to_resource_kinds=("dbfox.music.library",),
            tool_refs=(ToolKey("dbfox.music", "compose"),),
        ),
    )


def test_guidance_is_absent_without_relevant_runtime_facts() -> None:
    registry = ToolRegistry().register(_MusicTool(), owner="dbfox.music")
    tools = materialize_tools(
        registry,
        allowed_names=set(),
        execution_mode="agent_autonomous_read",
    )

    active = materialize_capability_guidance(
        (_guidance(),),
        resource_kinds=frozenset(),
        artifact_types=frozenset(),
        tools=tools,
        registry=registry,
    )

    assert active == ()


def test_guidance_uses_the_materialized_provider_wire_name_and_stable_hash() -> None:
    registry = ToolRegistry().register(_MusicTool(), owner="dbfox.music")
    tools = materialize_tools(
        registry,
        execution_mode="agent_autonomous_read",
        available_resource_kinds={"dbfox.music.library"},
    )

    first = materialize_capability_guidance(
        (_guidance(),),
        resource_kinds=frozenset({"dbfox.music.library"}),
        artifact_types=frozenset(),
        tools=tools,
        registry=registry,
    )
    second = materialize_capability_guidance(
        (_guidance(),),
        resource_kinds=frozenset({"dbfox.music.library"}),
        artifact_types=frozenset(),
        tools=tools,
        registry=registry,
    )

    assert len(first) == 1
    assert first == second
    assert first[0].tool_names == (("compose", tools.tools[0].name),)
    assert first[0].tool_names[0][1] != "compose"
    assert first[0].hash.startswith("sha256:")
