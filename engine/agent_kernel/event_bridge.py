from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from engine.agent.state import AgentState
from engine.agent.types import AgentApprovalRecord, AgentRuntimeEvent, ToolObservation


EmitRuntimeEvent = Callable[..., AgentRuntimeEvent]
StepNameResolver = Callable[[str], str]
ArtifactEventFactory = Callable[[ToolObservation, AgentState], Iterable[AgentRuntimeEvent]]


def events_from_graph_update(
    *,
    emit: EmitRuntimeEvent,
    node_name: str,
    update: dict[str, Any],
    agent_state: AgentState,
    step_name_for_tool: StepNameResolver,
    artifact_events: ArtifactEventFactory,
) -> Iterator[AgentRuntimeEvent]:
    if node_name == "policy" and isinstance(update.get("pending_approval"), dict):
        approval = AgentApprovalRecord.model_validate(update["pending_approval"])
        yield emit(
            "agent.approval.required",
            step={"name": approval.step_name, "status": "waiting_approval"},
            approval=approval,
        )

    if node_name != "execute_tool" or not isinstance(update.get("last_observation"), dict):
        return

    observation = ToolObservation.model_validate(update["last_observation"])
    tool_name = str(update.get("last_tool_name") or "")
    step_name = observation.name or step_name_for_tool(tool_name)
    yield emit("agent.step.started", step={"name": step_name, "tool_name": tool_name})
    agent_state.apply_observation(step_name, observation)
    yield emit(
        "agent.step.completed",
        step={
            "name": step_name,
            "tool_name": tool_name,
            "status": observation.status,
            "error": observation.error,
            "latency_ms": observation.latency_ms,
        },
    )
    yield from artifact_events(observation, agent_state)
