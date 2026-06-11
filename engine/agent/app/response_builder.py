from __future__ import annotations

from typing import Any

from engine.agent_core.types import (
    AgentAnswer,
    AgentApprovalRecord,
    AgentArtifact,
    AgentCheckpointRecord,
    AgentRunRequest,
    AgentRunResponse,
    AgentRunCanvas,
    PlanCard,
    TaskLensCard,
    ActivityStep,
    EvidenceItem,
    SafetyCheck,
    RecoveryRecord,
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

    summary_text = _merge_context_summaries(
        state=state,
        response_summary=build_response_context_summary(
            req=req,
            answer=explanation or (answer.answer if answer else None),
            artifacts=artifacts or [],
        ),
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
        "sql_revise": "revise_sql",
        "sql.revise": "revise_sql",
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
                if te.get("input"):
                    step_details[step_name]["input"] = te.get("input")
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

    canvas = build_canvas(state, final_steps, answer, run_id, session_id,
                          status or "completed", req.question)

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
        canvas=canvas,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Run Canvas builder (P5)
# ═══════════════════════════════════════════════════════════════════════════════


def build_canvas(
    state: dict[str, Any],
    steps: list[AgentStep],
    answer: AgentAnswer | None,
    run_id: str,
    session_id: str,
    status: str,
    question: str = "",
) -> AgentRunCanvas:
    """Build the AgentRunCanvas from final graph state + steps.

    Produces five cards that the frontend renders directly:
    - Plan Card: what the agent intended to do
    - Activity Timeline: chronological tool execution
    - Evidence Card: data backing the answer
    - Safety Card: validation and approval results
    - Recovery Card: failure diagnosis and retry history
    """
    # ── Plan Card ──────────────────────────────────────────────────────────
    plan_directive = state.get("plan_directive") or {}
    skill_ids: list[str] = state.get("selected_skill_ids") or []

    plan = PlanCard(
        task_type=plan_directive.get("task_type", ""),
        intent_summary=plan_directive.get("reasoning_summary", ""),
        execution_mode=plan_directive.get("execution_mode", ""),
        selected_skills=skill_ids,
        allowed_tool_groups=plan_directive.get("allowed_tool_groups") or [],
        forbidden_tool_groups=[],
        success_criteria=plan_directive.get("success_criteria") or [],
        risk_notes=plan_directive.get("risk_notes") or [],
        grounding_level=plan_directive.get("grounding_level", ""),
    )

    # ── Activity Timeline ──────────────────────────────────────────────────
    activity: list[ActivityStep] = []
    raw_traces = state.get("trace_events") or []
    step_outputs: dict[str, Any] = {}
    for s in steps:
        if s.output:
            step_outputs[s.name] = s.output

    for i, s in enumerate(steps):
        title = _activity_title(s.name)
        summary = _activity_summary(s.name, s.status, s.output)
        activity.append(ActivityStep(
            sequence=i + 1,
            step_name=s.name,
            tool_name=_step_to_tool(s.name),
            title=title,
            status=s.status,
            latency_ms=s.latency_ms,
            summary=summary,
            error=s.error[:200] if s.error else None,
        ))

    # ── Evidence Card ──────────────────────────────────────────────────────
    evidence: list[EvidenceItem] = []
    if answer and answer.evidence:
        for ev in answer.evidence:
            evidence.append(EvidenceItem(
                source="tool_result",
                label=ev.label,
                artifact_id=ev.artifact_id,
                value_summary=str(ev.value) if ev.value else None,
            ))
    # Add schema context as evidence
    schema_ctx = state.get("schema_context")
    if isinstance(schema_ctx, dict):
        tables = schema_ctx.get("selected_tables") or []
        if tables:
            evidence.append(EvidenceItem(
                source="schema_catalog",
                label=f"Schema context: {', '.join(str(t) for t in tables[:5])}",
            ))
    # Add execution result as evidence
    execution = state.get("execution")
    if isinstance(execution, dict) and execution.get("success"):
        rows = execution.get("rowCount", 0)
        if rows > 0:
            evidence.append(EvidenceItem(
                source="sql_execution",
                label=f"Query returned {rows} rows",
                value_summary=f"{rows} rows",
            ))

    # ── Safety Card ────────────────────────────────────────────────────────
    safety_checks: list[SafetyCheck] = []
    safety = state.get("safety")
    if isinstance(safety, dict):
        safety_checks.append(SafetyCheck(
            check_name="TrustGate",
            passed=bool(safety.get("can_execute")),
            detail=f"can_execute={safety.get('can_execute')}, "
                   f"requires_confirmation={safety.get('requires_confirmation')}",
            blocked_reasons=safety.get("blocked_reasons") or [],
            requires_approval=bool(safety.get("requires_confirmation")),
        ))
    # Policy blocked tools
    blocked = state.get("blocked_tool_calls") or []
    if blocked:
        safety_checks.append(SafetyCheck(
            check_name="PolicyGate",
            passed=False,
            detail=f"{len(blocked)} tool call(s) blocked by policy",
        ))
    # Approval state
    approval_result = state.get("approval_result") or {}
    if approval_result:
        safety_checks.append(SafetyCheck(
            check_name="Approval",
            passed=approval_result.get("status") == "approved",
            detail=f"Status: {approval_result.get('status', 'unknown')}",
            approval_status=approval_result.get("status"),
        ))

    # ── Task Lens (live focus, not an approval plan) ───────────────────────
    visible = state.get("visible_plan") or {}
    task_lens = TaskLensCard(
        goal=str(visible.get("goal") or "") if isinstance(visible, dict) else "",
        current_focus=str(visible.get("current_focus") or "") if isinstance(visible, dict) else "",
        next_likely=str(visible.get("next_likely") or "") if isinstance(visible, dict) else "",
        missing_evidence=list(visible.get("missing_evidence") or []) if isinstance(visible, dict) else [],
    )

    # ── Recovery Card ──────────────────────────────────────────────────────
    recovery: list[RecoveryRecord] = []
    progress = state.get("progress_decision") or {}
    if progress.get("status") in ("replan", "blocked", "failed"):
        recovery.append(RecoveryRecord(
            attempt=int(state.get("replan_count") or 0) + 1,
            failure_layer=progress.get("failure_layer") or "",
            root_cause=progress.get("root_cause") or str(state.get("error") or ""),
            recovery_strategy=progress.get("recovery_strategy") or "",
            retry_budget=int(progress.get("retry_budget") or 0),
            outcome="recovered" if progress.get("status") == "replan" else "finalized_with_caveat",
        ))

    repair_trace = state.get("repair_trace") or []
    if isinstance(repair_trace, list):
        repair_stats = state.get("repair_stats") or {}
        for i, entry in enumerate(repair_trace):
            if not isinstance(entry, dict):
                continue
            recovery.append(RecoveryRecord(
                attempt=int(entry.get("attempt") or repair_stats.get("attempts") or i + 1),
                failure_layer=str(entry.get("error_class") or repair_stats.get("last_error_class") or ""),
                root_cause=str(entry.get("user_visible_update") or entry.get("detail") or ""),
                recovery_strategy=str(
                    entry.get("recovery_strategy")
                    or repair_stats.get("recovery_strategy")
                    or ""
                ),
                retry_budget=int(repair_stats.get("max_attempts") or 3),
                outcome="recovered" if entry.get("type") == "agent.repair.prepared" else "in_progress",
            ))

    # ── Assemble ───────────────────────────────────────────────────────────
    total_ms = sum(s.latency_ms for s in steps)

    return AgentRunCanvas(
        run_id=run_id,
        session_id=session_id,
        status=status,
        plan=plan,
        task_lens=task_lens,
        activity=activity,
        evidence=evidence,
        safety=safety_checks,
        recovery=recovery,
        question=question,
        answer_summary=(answer.answer[:200] if answer and answer.answer else ""),
        total_latency_ms=total_ms,
        step_count=len(steps),
    )


# ── Canvas helpers ─────────────────────────────────────────────────────────────


def _activity_title(step_name: str) -> str:
    titles: dict[str, str] = {
        "build_schema_context": "Built schema context",
        "build_query_plan": "Built query plan",
        "generate_sql_candidate": "Generated SQL",
        "validate_sql": "Validated SQL",
        "execute_sql": "Executed query",
        "skip_execution": "Skipped execution",
        "revise_sql": "Revised SQL",
        "profile_result": "Profiled results",
        "suggest_chart": "Suggested chart",
        "suggest_followups": "Suggested follow-ups",
        "answer_synthesizer": "Synthesized answer",
        "list_tables": "Listed tables",
        "describe_table": "Described table",
        "refresh_catalog": "Refreshed catalog",
        "load_follow_up_context": "Loaded follow-up context",
        "memory_search": "Searched memory",
        "memory_write": "Wrote to memory",
        "memory_delete": "Deleted memory",
        "summarize_session": "Summarized session",
    }
    return titles.get(step_name, step_name.replace("_", " ").title())


def _activity_summary(step_name: str, status: str, output: Any) -> str:
    if status == "failed":
        return "Failed"
    if status == "skipped":
        return "Skipped"
    if output is None:
        return "Completed"
    if isinstance(output, dict):
        # Extract compact summary per step type
        if step_name == "build_schema_context":
            tables = output.get("selected_tables") or []
            return f"Selected {len(tables)} table(s)"
        if step_name == "build_query_plan":
            metrics = output.get("metrics") or []
            return f"Plan: {len(metrics)} metric(s)"
        if step_name == "generate_sql_candidate":
            sql = output.get("sql") or ""
            return f"SQL: {len(sql)} chars"
        if step_name == "validate_sql":
            return "Passed" if output.get("can_execute") else "Blocked"
        if step_name == "execute_sql":
            return f"{output.get('rowCount', 0)} rows"
        if step_name == "profile_result":
            facts = output.get("notable_facts") or []
            return f"{len(facts)} notable fact(s)"
        if step_name == "suggest_chart":
            return f"Chart: {output.get('type', '?')}"
        if step_name == "answer_synthesizer":
            ans = output.get("answer", "")
            return ans[:80] + ("..." if len(ans) > 80 else "")
        if step_name == "list_tables":
            tables = output.get("tables") or []
            return f"{len(tables)} tables"
        if step_name == "describe_table":
            cols = output.get("columns") or []
            return f"{len(cols)} columns"
    return "Completed"


def _step_to_tool(step_name: str) -> str:
    mapping = {
        "build_schema_context": "schema.build_context",
        "build_query_plan": "query_plan.build",
        "generate_sql_candidate": "sql.generate",
        "validate_sql": "sql.validate",
        "execute_sql": "sql.execute_readonly",
        "skip_execution": "sql.skip_execution",
        "revise_sql": "sql.revise",
        "profile_result": "result.profile",
        "suggest_chart": "chart.suggest",
        "suggest_followups": "followup.suggest",
        "answer_synthesizer": "answer.synthesize",
        "list_tables": "schema.list_tables",
        "describe_table": "schema.describe_table",
        "refresh_catalog": "schema.refresh_catalog",
        "load_follow_up_context": "followup.load_context",
        "memory_search": "memory.search",
        "memory_write": "memory.write",
        "memory_delete": "memory.delete",
        "summarize_session": "memory.summarize_session",
    }
    return mapping.get(step_name, step_name)


def _merge_context_summaries(*, state: dict[str, Any], response_summary: str) -> str:
    """Prepend ContextPack ui_summary and visible plan focus to the response summary."""
    parts: list[str] = []

    pack = state.get("context_pack")
    if isinstance(pack, dict):
        ui_summary = pack.get("ui_summary")
        if isinstance(ui_summary, str) and ui_summary.strip():
            parts.append(ui_summary.strip())

    visible = state.get("visible_plan") or {}
    if isinstance(visible, dict):
        focus = visible.get("current_focus")
        if isinstance(focus, str) and focus.strip():
            if not parts or focus.strip() not in parts[0]:
                parts.append(f"Focus: {focus.strip()}")

    repair_trace = state.get("repair_trace") or []
    if isinstance(repair_trace, list) and repair_trace:
        last = repair_trace[-1]
        if isinstance(last, dict) and last.get("user_visible_update"):
            repair_note = str(last["user_visible_update"])
            if repair_note not in " ".join(parts):
                parts.append(f"Repair: {repair_note}")

    if response_summary:
        parts.append(response_summary)

    return " | ".join(parts) if parts else response_summary
