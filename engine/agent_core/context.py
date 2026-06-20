from __future__ import annotations

from typing import Any

from engine.agent_core.types import AgentArtifact, AgentRunRequest


MAX_CONTEXT_CHARS = 2400
MAX_ARTIFACT_SUMMARY_CHARS = 360


def has_follow_up_context(req: AgentRunRequest) -> bool:
    context = req.follow_up_context
    return bool(
        context
        and (
            context.previous_question
            or context.previous_answer
            or context.artifacts
        )
    )


def schema_linking_question(req: AgentRunRequest) -> str:
    if not has_follow_up_context(req):
        return req.question

    context = req.follow_up_context
    if context is None:
        return req.question

    parts = [req.question]
    if context.previous_question:
        parts.append(context.previous_question)
    for artifact in context.artifacts[:4]:
        parts.append(f"{artifact.title} {artifact.summary or ''}")
    return _compact_text(" ".join(parts), MAX_CONTEXT_CHARS)


def analysis_question(req: AgentRunRequest) -> str:
    if not has_follow_up_context(req):
        return req.question

    context = req.follow_up_context
    if context is None:
        return req.question

    lines = [f"Current question: {req.question}", "Use this prior turn only as context for the current question."]
    if context.previous_question:
        lines.append(f"Previous question: {context.previous_question}")
    if context.previous_answer:
        lines.append(f"Previous answer: {context.previous_answer}")
    if context.artifacts:
        lines.append("Prior artifacts:")
        for artifact in context.artifacts[:8]:
            summary = _compact_text(artifact.summary or _summarize_payload(artifact.payload), MAX_ARTIFACT_SUMMARY_CHARS)
            lines.append(f"- {artifact.id} ({artifact.type}, {artifact.title}): {summary}")
    return _compact_text("\n".join(lines), MAX_CONTEXT_CHARS)


def context_summary(req: AgentRunRequest) -> str | None:
    if not has_follow_up_context(req):
        return None
    context = req.follow_up_context
    if context is None:
        return None
    artifact_ids = [artifact.id for artifact in context.artifacts[:8]]
    pieces = []
    if context.previous_question:
        pieces.append(f"previous question: {context.previous_question}")
    if context.previous_answer:
        pieces.append(f"previous answer available")
    if artifact_ids:
        pieces.append(f"artifacts: {', '.join(artifact_ids)}")
    return "; ".join(pieces) or None


def referenced_artifact_ids(req: AgentRunRequest) -> list[str]:
    context = req.follow_up_context
    if context is None:
        return []
    return [artifact.id for artifact in context.artifacts]


def build_response_context_summary(
    req: AgentRunRequest,
    answer: str | None,
    artifacts: list[AgentArtifact],
) -> str:
    lines = [f"Question: {req.question}"]
    if answer:
        lines.append(f"Answer: {answer}")
    if artifacts:
        lines.append("Artifacts:")
        for artifact in artifacts[:8]:
            summary = _compact_text(_summarize_payload(artifact.payload), MAX_ARTIFACT_SUMMARY_CHARS)
            lines.append(f"- {artifact.id} ({artifact.type}, {artifact.title}): {summary}")
    return _compact_text("\n".join(lines), MAX_CONTEXT_CHARS)


def _summarize_payload(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    if isinstance(payload.get("sql"), str):
        return str(payload["sql"])
    if "rowCount" in payload or "columns" in payload:
        columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
        return f"rowCount={payload.get('rowCount')}; columns={', '.join(str(item) for item in columns[:8])}"  # type: ignore[index]
    if "can_execute" in payload:
        return f"can_execute={payload.get('can_execute')}; messages={payload.get('messages')}"
    if "error" in payload:
        return str(payload.get("error") or "")
    return ", ".join(f"{key}={value}" for key, value in list(payload.items())[:6])


def _compact_text(value: str, max_chars: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."
