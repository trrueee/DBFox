from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from engine.agent.registry import AgentToolContext, ToolRegistry
from engine.agent.state import AgentState
from engine.agent.types import AgentStep, ToolObservation


class AgentStepSpec(BaseModel):
    name: str
    tool_name: str
    input_builder: str | None = None
    required: bool = True
    skip_when: str | None = None


class StepExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute_step(
        self,
        step: AgentStepSpec,
        state: AgentState,
        ctx: AgentToolContext,
        input_override: dict[str, Any] | None = None,
    ) -> tuple[AgentStep, ToolObservation]:
        tool_input = input_override or {}
        ctx.state = state
        started = time.perf_counter()
        try:
            tool = self.registry.get(step.tool_name)
            observation = tool.execute(tool_input, ctx)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            observation = ToolObservation(
                name=step.name,
                status="failed",
                input=tool_input,
                output=None,
                error=str(exc),
                latency_ms=latency_ms,
            )

        agent_step = AgentStep(
            name=observation.name or step.name,
            status=observation.status,
            input=observation.input,
            output=observation.output,
            error=observation.error,
            latency_ms=observation.latency_ms,
        )
        return agent_step, observation
