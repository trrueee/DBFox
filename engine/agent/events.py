from __future__ import annotations

import time

from engine.agent.types import AgentStep, AgentTraceEvent


def build_trace_events(steps: list[AgentStep]) -> list[AgentTraceEvent]:
    events: list[AgentTraceEvent] = []
    created_at_ms = _now_ms()
    for index, step in enumerate(steps, start=1):
        step_id = f"step_{index}_{step.name}"
        started_sequence = len(events) + 1
        events.append(
            AgentTraceEvent(
                event_id=f"trace_{started_sequence}_{step_id}_started",
                sequence=started_sequence,
                created_at_ms=created_at_ms + started_sequence,
                type="agent.trace.step_started",
                step_id=step_id,
                name=step.name,
                input=step.input,
            )
        )
        completed_sequence = len(events) + 1
        events.append(
            AgentTraceEvent(
                event_id=f"trace_{completed_sequence}_{step_id}_completed",
                sequence=completed_sequence,
                created_at_ms=created_at_ms + completed_sequence,
                type="agent.trace.step_completed",
                step_id=step_id,
                name=step.name,
                status=step.status,
                input=step.input,
                output=step.output,
                error=step.error,
                latency_ms=step.latency_ms,
            )
        )
    return events


def _now_ms() -> int:
    return int(time.time() * 1000)
