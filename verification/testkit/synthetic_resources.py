"""Capability-neutral resources and tools for frozen-authority benchmarks."""

from __future__ import annotations

from engine.errors import ToolInputError
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPresentation,
    ToolRunContext,
)


SYNTHETIC_RESOURCE_KIND = "verification.resource"


class ResourceProbeInput(ToolInputModel):
    resource_id: str


class ResourceProbeOutput(ToolOutputModel):
    resource_id: str
    value: str


class ResourceProbeTool(BaseTool[ResourceProbeInput, ResourceProbeOutput]):
    name = "verification_resource_probe"
    group = "verification"
    description = "Read one explicitly selected capability-neutral authorized resource."
    input_model = ResourceProbeInput
    output_model = ResourceProbeOutput
    presentation = ToolPresentation(title="Resource probe", category="explore")
    execution = ToolExecutionSpec(required_resource_kinds=(SYNTHETIC_RESOURCE_KIND,))

    def __init__(self, access_log: list[str]) -> None:
        self._access_log = access_log

    def run(
        self,
        tool_input: ResourceProbeInput,
        context: ToolRunContext,
    ) -> ResourceProbeOutput:
        scope = context.scope(SYNTHETIC_RESOURCE_KIND, tool_input.resource_id)
        if scope is None:
            raise ToolInputError("The requested verification resource is not authorized.")
        resource = context.resource(scope)
        if not isinstance(resource, dict) or resource.get("id") != tool_input.resource_id:
            raise RuntimeError("The verification resource resolver returned the wrong identity")
        self._access_log.append(tool_input.resource_id)
        return ResourceProbeOutput(
            resource_id=tool_input.resource_id,
            value=str(resource.get("value") or ""),
        )
