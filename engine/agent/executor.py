from __future__ import annotations

import logging
import time
import traceback
from typing import Any

from pydantic import BaseModel

from engine.agent.registry import AgentToolContext, ToolRegistry
from engine.agent.state import AgentState
from engine.agent.types import AgentErrorOutput, AgentStep, ToolObservation

logger = logging.getLogger("databox.agent.executor")


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
            error_type = type(exc).__name__
            error_traceback = traceback.format_exc()
            retryable = _is_retryable_exception(exc)
            logger.exception(
                "Agent step execution failed: step=%s tool=%s error_type=%s retryable=%s",
                step.name,
                step.tool_name,
                error_type,
                retryable,
            )
            error_output = AgentErrorOutput(
                error_type=error_type,
                tool_name=step.tool_name,
                step_name=step.name,
                traceback=error_traceback,
                retryable=retryable,
                retry_reason="transient_database_or_connection_error" if retryable else None,
            )
            observation = ToolObservation(
                name=step.name,
                status="failed",
                input=tool_input,
                output=error_output.model_dump(mode="json"),
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


def _is_retryable_exception(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    retry_tokens = (
        "timeout",
        "temporarily",
        "temporary",
        "connection reset",
        "connection refused",
        "connection aborted",
        "deadlock",
        "lock wait timeout",
        "too many connections",
        "server has gone away",
        "operationalerror",
    )
    return any(token in name or token in message for token in retry_tokens)
