from __future__ import annotations

import time
from typing import Any, Callable

from engine.agent_core.types import (
    AgentAnswer,
    AgentApprovalRecord,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunResponse,
    AgentRuntimeEvent,
    AgentRuntimeEventType,
    AgentStep,
    AgentTraceEvent,
)
from engine.agent_core.trace_redactor import AgentTraceRedactor


RuntimeEventRecorder = Callable[[AgentRuntimeEvent], None]


class EventEmitter:
    def __init__(
        self,
        run_id: str,
        recorder: RuntimeEventRecorder | None = None,
        start_sequence: int = 0,
    ):
        self.run_id = run_id
        self.recorder = recorder
        self.sequence = start_sequence

    def emit(
        self,
        event_type: AgentRuntimeEventType,
        *,
        step: dict[str, Any] | None = None,
        artifact: AgentArtifact | None = None,
        artifact_delta: dict[str, Any] | None = None,
        answer_payload: AgentAnswer | None = None,
        response: AgentRunResponse | None = None,
        approval: AgentApprovalRecord | None = None,
        checkpoint: AgentCheckpointRecord | None = None,
        error: str | None = None,
    ) -> AgentRuntimeEvent:
        self.sequence += 1
        event = AgentRuntimeEvent(
            event_id=f"runtime_{self.run_id[:8]}_{self.sequence}_{event_type.replace('.', '_')}",
            run_id=self.run_id,
            sequence=self.sequence,
            created_at_ms=_now_ms(),
            type=event_type,
            step=step,
            artifact=artifact,
            artifact_delta=artifact_delta,
            answer=answer_payload,
            response=response,
            approval=approval,
            checkpoint=checkpoint,
            error=error,
        )
        if self.recorder is not None:
            self.recorder(event)
        return event


def build_trace_events(
    steps: list[AgentStep],
    redactor: AgentTraceRedactor | None = None,
) -> list[AgentTraceEvent]:
    redactor = redactor or AgentTraceRedactor()
    events: list[AgentTraceEvent] = []
    created_at_ms = _now_ms()
    for index, step in enumerate(steps, start=1):
        step_id = f"step_{index}_{step.name}"
        started_sequence = len(events) + 1
        events.append(
            _trace_event(
                redactor,
                event_id=f"trace_{started_sequence}_{step_id}_started",
                sequence=started_sequence,
                created_at_ms=created_at_ms + started_sequence,
                event_type="agent.trace.step_started",
                step_id=step_id,
                name=step.name,
                input=step.input,
            )
        )
        completed_sequence = len(events) + 1
        events.append(
            _trace_event(
                redactor,
                event_id=f"trace_{completed_sequence}_{step_id}_completed",
                sequence=completed_sequence,
                created_at_ms=created_at_ms + completed_sequence,
                event_type="agent.trace.step_completed",
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


def _trace_event(
    redactor: AgentTraceRedactor,
    event_id: str,
    sequence: int,
    created_at_ms: int,
    event_type: str,
    step_id: str,
    name: str,
    status: str | None = None,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    latency_ms: int | None = None,
) -> AgentTraceEvent:
    event_data = {
        "event_id": event_id,
        "sequence": sequence,
        "created_at_ms": created_at_ms,
        "type": event_type,
        "step_id": step_id,
        "name": name,
        "status": status,
        "input": redactor.redact(input) if input is not None else None,
        "output": redactor.redact(output) if output is not None else None,
        "error": redactor.redact(error) if error is not None else None,
        "latency_ms": latency_ms,
    }
    return AgentTraceEvent.model_validate(redactor.cap_event(event_data))


def _now_ms() -> int:
    return int(time.time() * 1000)
