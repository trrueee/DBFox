from __future__ import annotations

from typing import Any

from engine.agent_core.types import (
    AgentAnswer,
    AgentApprovalRecord,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    AnswerEvidence,
    FollowUpSuggestion,
    ResultProfile,
    AgentVisibleEvent,
    AgentMessageBlock,
    AgentTraceEvent,
)
from engine.agent_core.artifacts import AgentArtifactIdentity
from engine.agent_core.context import build_response_context_summary, referenced_artifact_ids


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
        evidence_mapped = []
        for item in (answer_raw.get("evidence") or []):
            if isinstance(item, dict):
                art_id = item.get("artifact_id")
                label = item.get("label")
                val = item.get("value")
            else:
                art_id = getattr(item, "artifact_id", None)
                label = getattr(item, "label", None)
                val = getattr(item, "value", None)
            
            if artifacts and art_id:
                for art in artifacts:
                    if art.semantic_id == art_id:
                        art_id = art.id
                        break
            evidence_mapped.append(AnswerEvidence(artifact_id=art_id, label=label or "", value=val))

        answer = AgentAnswer(
            answer=str(answer_raw.get("answer") or ""),
            key_findings=answer_raw.get("key_findings") or [],
            evidence=evidence_mapped,
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

    summary_text = build_response_context_summary(
        req=req,
        answer=explanation or (answer.answer if answer else None),
        artifacts=artifacts or [],
    )

    # Map raw trace events in state to AgentStep and AgentTraceEvent
    tool_to_step_name = {
        "schema_build_context": "build_schema_context",
        "schema.build_context": "build_schema_context",
        "sql_generate": "generate_sql_candidate",
        "sql.generate": "generate_sql_candidate",
        "sql_validate": "validate_sql",
        "sql.validate": "validate_sql",
        "sql_execute_readonly": "execute_sql",
        "sql.execute_readonly": "execute_sql",
        "sql_skip_execution": "execute_sql",
        "sql.skip_execution": "execute_sql",
        "result_profile": "profile_result",
        "result.profile": "profile_result",
        "chart_suggest": "suggest_chart",
        "chart.suggest": "suggest_chart",
        "followup_suggest": "suggest_followups",
        "followup.suggest": "suggest_followups",
        "followup_load_context": "load_follow_up_context",
        "followup.load_context": "load_follow_up_context",
        "answer_synthesize": "answer_synthesizer",
        "answer.synthesize": "answer_synthesizer",
    }

    raw_traces = state.get("trace_events") or []
    ordered_step_names = []
    step_details = {}
    for te in raw_traces:
        if not isinstance(te, dict):
            continue
        te_type = te.get("type")
        tool_name = te.get("tool_name")
        if te_type in ("agent.tool.started", "agent.tool.completed") and tool_name:
            step_name = tool_to_step_name.get(tool_name, tool_name)
            if step_name not in step_details:
                ordered_step_names.append(step_name)
                step_details[step_name] = {
                    "status": "success",
                    "latency_ms": 0,
                    "input": te.get("input"),
                    "output": te.get("output"),
                    "error": te.get("error"),
                }
            if te_type == "agent.tool.completed":
                step_details[step_name]["status"] = te.get("status") or "success"
                step_details[step_name]["latency_ms"] = te.get("latency_ms") or 0
                if te.get("error"):
                    step_details[step_name]["error"] = te.get("error")
                if te.get("output"):
                    step_details[step_name]["output"] = te.get("output")

    steps_list = []
    for step_name in ordered_step_names:
        details = step_details[step_name]
        steps_list.append(AgentStep(
            name=step_name,
            status=details["status"],
            latency_ms=details["latency_ms"],
            input=details["input"],
            output=details["output"],
            error=details["error"],
        ))

    final_steps = steps_list if steps_list else (steps or [])

    # Build events list
    events = []
    seq = 1
    # 1. Narration completed
    events.append(AgentVisibleEvent(
        event_id=f"evt-{seq}",
        sequence=seq,
        type="agent.narration.completed",
        content=explanation or "I have processed your request.",
    ))
    seq += 1
    # 2. Artifact created events
    for art in (artifacts or []):
        events.append(AgentVisibleEvent(
            event_id=f"evt-{seq}",
            sequence=seq,
            type="agent.artifact.created",
            artifact=art,
        ))
        seq += 1
    # 3. Answer completed
    if answer:
        events.append(AgentVisibleEvent(
            event_id=f"evt-{seq}",
            sequence=seq,
            type="agent.answer.completed",
            answer=answer,
        ))
        seq += 1
    # 4. Suggestions created
    if suggestions:
        events.append(AgentVisibleEvent(
            event_id=f"evt-{seq}",
            sequence=seq,
            type="agent.suggestions.created",
            suggestions=suggestions,
        ))
        seq += 1

    # Build message blocks
    message_blocks = []
    blk_seq = 1
    # 1. Text block
    message_blocks.append(AgentMessageBlock(
        block_id=f"blk-{blk_seq}",
        sequence=blk_seq,
        type="text",
        content=explanation or "Here is the response to your request.",
    ))
    blk_seq += 1
    # 2. Artifact references
    for art in (artifacts or []):
        message_blocks.append(AgentMessageBlock(
            block_id=f"blk-{blk_seq}",
            sequence=blk_seq,
            type="artifact_ref",
            artifact_id=art.id,
            content=art.title,
        ))
        blk_seq += 1
    # 3. Answer block
    if answer:
        message_blocks.append(AgentMessageBlock(
            block_id=f"blk-{blk_seq}",
            sequence=blk_seq,
            type="answer",
            answer=answer,
        ))
        blk_seq += 1
    # 4. Suggestions block
    if suggestions:
        message_blocks.append(AgentMessageBlock(
            block_id=f"blk-{blk_seq}",
            sequence=blk_seq,
            type="suggestions",
            suggestions=suggestions,
        ))
        blk_seq += 1

    # Build trace events
    trace_events = []
    te_seq = 1
    for i, step in enumerate(final_steps):
        step_id = f"step-{i}"
        # Step started
        trace_events.append(AgentTraceEvent(
            event_id=f"te-{te_seq}",
            sequence=te_seq,
            type="agent.trace.step_started",
            step_id=step_id,
            name=step.name,
        ))
        te_seq += 1
        # Step completed
        trace_events.append(AgentTraceEvent(
            event_id=f"te-{te_seq}",
            sequence=te_seq,
            type="agent.trace.step_completed",
            step_id=step_id,
            name=step.name,
            status=step.status,
            latency_ms=step.latency_ms,
            input=step.input,
            output=step.output,
            error=step.error,
        ))
        te_seq += 1

    return AgentRunResponse(
        run_id=run_id,
        session_id=session_id,
        parent_run_id=req.parent_run_id,
        success=success,
        status=status or ("completed" if success else "failed"),
        question=req.question,
        context_summary=summary_text,
        referenced_artifact_ids=referenced_artifact_ids(req),
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
        message_blocks=message_blocks,
        events=events,
        trace_events=trace_events,
        steps=final_steps,
        error=error,
        approval=approval,
        checkpoint=checkpoint,
        approval_context=None,
    )
