from __future__ import annotations

import time
from typing import Any

from engine.agent.types import AgentAnswer, AgentArtifact, AgentMessageBlock, AgentStep, AgentVisibleEvent, FollowUpSuggestion


def build_visible_events(
    question: str,
    steps: list[AgentStep],
    artifacts: list[AgentArtifact],
    answer: AgentAnswer | None,
    suggestions: list[FollowUpSuggestion],
    error: str | None = None,
) -> list[AgentVisibleEvent]:
    created_at_ms = _now_ms()
    events: list[AgentVisibleEvent] = []
    events.append(
        _visible_event(
            sequence=len(events) + 1,
            created_at_ms=created_at_ms,
            event_type="agent.narration.completed",
            content=_opening_narration(question, steps, error),
        )
    )

    for artifact in artifacts:
        if artifact.presentation.mode in ("inline", "both"):
            events.append(
                _visible_event(
                    sequence=len(events) + 1,
                    created_at_ms=created_at_ms,
                    event_type="agent.artifact.created",
                    artifact=artifact,
                )
            )

    if answer:
        events.append(
            _visible_event(
                sequence=len(events) + 1,
                created_at_ms=created_at_ms,
                event_type="agent.answer.completed",
                answer=answer,
            )
        )

    if suggestions:
        events.append(
            _visible_event(
                sequence=len(events) + 1,
                created_at_ms=created_at_ms,
                event_type="agent.suggestions.created",
                suggestions=suggestions,
            )
        )

    return events


def build_message_blocks(events: list[AgentVisibleEvent]) -> list[AgentMessageBlock]:
    blocks: list[AgentMessageBlock] = []
    for event in events:
        if event.type in ("agent.narration.completed", "agent.narration.delta") and event.content:
            blocks.append(
                _message_block(
                    sequence=len(blocks) + 1,
                    block_type="text",
                    content=event.content,
                )
            )
        elif event.type == "agent.artifact.created" and event.artifact:
            blocks.append(
                _message_block(
                    sequence=len(blocks) + 1,
                    block_type="artifact_ref",
                    artifact_id=event.artifact.id,
                    display=_artifact_display(event.artifact),
                )
            )
        elif event.type == "agent.answer.completed" and event.answer:
            blocks.append(
                _message_block(
                    sequence=len(blocks) + 1,
                    block_type="answer",
                    answer=event.answer,
                )
            )
        elif event.type == "agent.suggestions.created" and event.suggestions:
            blocks.append(
                _message_block(
                    sequence=len(blocks) + 1,
                    block_type="suggestions",
                    suggestions=event.suggestions,
                )
            )
    return blocks


def _visible_event(
    sequence: int,
    created_at_ms: int,
    event_type: str,
    content: str | None = None,
    artifact: AgentArtifact | None = None,
    answer: AgentAnswer | None = None,
    suggestions: list[FollowUpSuggestion] | None = None,
) -> AgentVisibleEvent:
    return AgentVisibleEvent(
        event_id=f"visible_{sequence}_{event_type.replace('.', '_')}",
        sequence=sequence,
        created_at_ms=created_at_ms + sequence,
        type=event_type,  # type: ignore[arg-type]
        content=content,
        artifact=artifact,
        answer=answer,
        suggestions=suggestions or [],
    )


def _message_block(
    sequence: int,
    block_type: str,
    content: str | None = None,
    artifact_id: str | None = None,
    display: str | None = None,
    answer: AgentAnswer | None = None,
    suggestions: list[FollowUpSuggestion] | None = None,
) -> AgentMessageBlock:
    return AgentMessageBlock(
        block_id=f"block_{sequence}_{block_type}",
        sequence=sequence,
        type=block_type,  # type: ignore[arg-type]
        content=content,
        artifact_id=artifact_id,
        display=display,  # type: ignore[arg-type]
        answer=answer,
        suggestions=suggestions or [],
    )


def _artifact_display(artifact: AgentArtifact) -> str:
    if artifact.presentation.collapsed or artifact.type in ("query_plan", "sql", "safety"):
        return "compact"
    return "full"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _opening_narration(question: str, steps: list[AgentStep], error: str | None) -> str:
    if error:
        return f"I started from the trusted schema and safety checks, but stopped before a complete answer: {error}"

    tables = _selected_tables(steps)
    if tables:
        return f"I used the trusted schema context around {', '.join(tables[:4])} to answer: {question}"
    return f"I translated the question into a validated data analysis path: {question}"


def _selected_tables(steps: list[AgentStep]) -> list[str]:
    for step in steps:
        if step.name == "build_schema_context" and step.output:
            selected = step.output.get("selected_tables")
            if isinstance(selected, list):
                return [str(table) for table in selected]
        if step.name == "build_query_plan" and step.output:
            selected = step.output.get("candidate_tables")
            if isinstance(selected, list):
                return [str(table) for table in selected]
    return []
