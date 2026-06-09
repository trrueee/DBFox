from __future__ import annotations

from typing import Any

from engine.agent.types import (
    AgentAnswer,
    AgentApprovalRecord,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    FollowUpSuggestion,
    ResultProfile,
)
from engine.agent.artifacts import AgentArtifactIdentity


def build_response(
    *,
    req: AgentRunRequest,
    run_id: str,
    session_id: str,
    state: dict[str, Any],
    steps: list[AgentStep] | None = None,
    artifacts: list[AgentArtifact] | None = None,
    approval: AgentApprovalRecord | None = None,
    checkpoint: AgentCheckpointRecord | None = None,
    success: bool = True,
    error: str | None = None,
    status: str | None = None,
) -> AgentRunResponse:
    """Build an AgentRunResponse from final graph state."""

    answer_raw = state.get("answer") or state.get("final_answer") or {}

    if isinstance(answer_raw, dict):
        answer = AgentAnswer(
            answer=str(answer_raw.get("answer") or ""),
            key_findings=answer_raw.get("key_findings") or [],
            evidence=answer_raw.get("evidence") or [],
            caveats=answer_raw.get("caveats") or [],
            recommendations=answer_raw.get("recommendations") or [],
            follow_up_questions=answer_raw.get("follow_up_questions") or [],
        )
    else:
        answer = AgentAnswer(answer=str(answer_raw or ""))

    suggestions_raw = state.get("suggestions") or []
    suggestions = [
        FollowUpSuggestion.model_validate(item) if isinstance(item, dict) else item
        for item in suggestions_raw
    ]

    sql = state.get("sql")
    if isinstance(sql, dict):
        sql = str(sql.get("sql") or "")

    explanation = None
    if isinstance(answer_raw, dict):
        explanation = str(answer_raw.get("answer") or "")

    return AgentRunResponse(
        run_id=run_id,
        session_id=session_id,
        parent_run_id=req.parent_run_id,
        success=success,
        status=status or ("completed" if success else "failed"),
        question=req.question,
        context_summary=None,
        referenced_artifact_ids=[],
        query_plan=state.get("query_plan") if isinstance(state.get("query_plan"), dict) else None,
        sql=sql if isinstance(sql, str) else None,
        safety=state.get("safety") if isinstance(state.get("safety"), dict) else None,
        execution=state.get("execution") if isinstance(state.get("execution"), dict) else None,
        explanation=explanation,
        chart_suggestion=state.get("chart_suggestion") if isinstance(state.get("chart_suggestion"), dict) else None,
        result_profile=state.get("result_profile") if isinstance(state.get("result_profile"), dict) else None,
        answer=answer,
        suggestions=suggestions,
        artifacts=artifacts or [],
        message_blocks=[],
        events=[],
        trace_events=[],
        steps=steps or [],
        error=error,
        approval=approval,
        checkpoint=checkpoint,
        approval_context=None,
    )
