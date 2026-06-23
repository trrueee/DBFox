from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and not item.get("__clear__")]


def _format_conversation_memory(state: dict[str, Any]) -> str:
    summary = state.get("conversation_summary")
    recent_turns = _list_dicts(state.get("recent_turns"))
    sql_refs = _list_dicts(state.get("sql_ref_index"))
    artifact_refs = _list_dicts(state.get("artifact_ref_index"))
    active_task = state.get("active_task")

    if not summary and not recent_turns and not sql_refs and not artifact_refs and not active_task:
        return ""

    parts = ["### Conversation Memory"]
    if summary:
        parts.append(f"- **Summary**: {summary}")
    if isinstance(active_task, dict) and active_task:
        parts.append(f"- **Active task**: {active_task}")

    if recent_turns:
        parts.append("- **Recent turns**:")
        for turn in recent_turns[-4:]:
            question = str(turn.get("question") or "").strip()
            answer = str(turn.get("answer") or "").strip()
            sql_fingerprints = ", ".join(str(item) for item in (turn.get("sql_fingerprints") or [])[:4])
            artifact_ids = ", ".join(str(item) for item in (turn.get("artifact_ids") or [])[:4])
            if question or answer:
                parts.append(f"  - user: {question}")
                if answer:
                    parts.append(f"    assistant: {answer}")
            if sql_fingerprints:
                parts.append(f"    sql_fingerprints: {sql_fingerprints}")
            if artifact_ids:
                parts.append(f"    artifact_ids: {artifact_ids}")

    if sql_refs:
        parts.append("- **Reusable SQL refs**:")
        for ref in sql_refs[:5]:
            purpose = ref.get("purpose") or ref.get("question") or ref.get("id") or "SQL ref"
            tables = ", ".join(str(t) for t in (ref.get("tables") or ref.get("involved_tables") or [])[:6])
            columns = ", ".join(str(c) for c in (ref.get("columns") or ref.get("result_columns") or [])[:8])
            safe_sql = str(ref.get("safe_sql") or "").strip()
            if len(safe_sql) > 800:
                safe_sql = safe_sql[:797] + "..."
            parts.append(f"  - {purpose}")
            if tables:
                parts.append(f"    - tables: {tables}")
            if columns:
                parts.append(f"    - columns: {columns}")
            if safe_sql:
                parts.append(f"    - sql: ```sql\n{safe_sql}\n```")

    if artifact_refs:
        parts.append("- **SQL-backed artifact refs**:")
        for ref in artifact_refs[:5]:
            artifact_id = ref.get("artifact_id") or ref.get("id")
            source_sql_id = ref.get("source_sql_artifact_id")
            columns = ", ".join(str(c) for c in (ref.get("columns") or [])[:8])
            detail = f"  - artifact={artifact_id}"
            if source_sql_id:
                detail += f", source_sql={source_sql_id}"
            if columns:
                detail += f", columns={columns}"
            parts.append(detail)

    return "\n".join(parts)


def _format_reusable_sql_candidates(state: dict[str, Any]) -> str:
    candidates = _list_dicts(state.get("reusable_sql_candidates"))
    if not candidates:
        return ""

    parts = ["### Datasource Reusable SQL"]
    for candidate in candidates[:5]:
        purpose = candidate.get("purpose") or candidate.get("question") or candidate.get("id") or "reusable SQL"
        usage_count = candidate.get("usage_count")
        tables = ", ".join(str(t) for t in (candidate.get("tables") or [])[:6])
        columns = ", ".join(str(c) for c in (candidate.get("columns") or [])[:8])
        safe_sql = str(candidate.get("safe_sql") or "").strip()
        if len(safe_sql) > 800:
            safe_sql = safe_sql[:797] + "..."
        header = f"- {purpose}"
        if usage_count is not None:
            header += f" (usage_count={usage_count})"
        parts.append(header)
        if tables:
            parts.append(f"  - tables: {tables}")
        if columns:
            parts.append(f"  - columns: {columns}")
        if safe_sql:
            parts.append(f"  - sql: ```sql\n{safe_sql}\n```")
    return "\n".join(parts)


def build_progress_guidance_message(state: dict[str, Any]) -> SystemMessage | None:
    """Inject Progress Judge supervisor output into the next model turn."""
    progress = state.get("progress_decision") or {}
    status = progress.get("status")
    if status not in ("continue", "replan"):
        return None

    parts = ["### Progress Supervisor Guidance"]
    hint = progress.get("next_action_hint") or progress.get("next_instruction")
    if hint:
        parts.append(f"- **Next action**: {hint}")

    missing = progress.get("missing_evidence") or []
    if missing:
        parts.append(f"- **Missing evidence**: {', '.join(str(m) for m in missing[:5])}")

    recovery = progress.get("recovery_strategy")
    if recovery:
        parts.append(f"- **Recovery strategy**: {recovery}")

    if progress.get("failure_layer"):
        parts.append(f"- **Failure layer**: {progress['failure_layer']}")
    if progress.get("root_cause"):
        parts.append(f"- **Root cause**: {progress['root_cause']}")

    if state.get("repair_mode"):
        parts.append(
            "- **Mode**: SQL repair active — use schema tools as needed, then produce corrected SQL, call sql.validate, and call sql.execute_readonly only after validation succeeds."
        )

    repair_trace = state.get("repair_trace") or []
    if repair_trace:
        parts.append("### SQL Repair History")
        for entry in repair_trace[-3:]:
            if isinstance(entry, dict):
                parts.append(
                    f"- Attempt {entry.get('attempt', '?')}: "
                    f"{entry.get('error_class', 'error')} — "
                    f"{entry.get('user_visible_update') or entry.get('recovery_strategy', '')}"
                )

    reason = progress.get("reason_summary")
    if reason:
        parts.append(f"- **Assessment**: {reason}")

    if len(parts) == 1:
        return None
    return SystemMessage(content="\n".join(parts))


def build_context_message(state: dict[str, Any]) -> SystemMessage:
    """Format the factual DBFox business state variables into a SystemMessage context block.

    This ensures the LLM stays grounded in actual tool output and execution history.

    When a ContextPack is available in state (Agent v2), uses its structured
    model view.  Falls back to ad-hoc state assembly for backward compatibility.
    """
    # Agent v2: use ContextPack when available
    context_pack_raw = state.get("context_pack")
    if context_pack_raw and isinstance(context_pack_raw, dict):
        try:
            from engine.agent.context_pack import ContextPack, render_for_model
            pack = ContextPack.model_validate(context_pack_raw)
            content = render_for_model(pack)
            memory_context = _format_conversation_memory(state)
            if memory_context:
                content = f"{content}\n\n{memory_context}"
            reusable_sql_context = _format_reusable_sql_candidates(state)
            if reusable_sql_context:
                content = f"{content}\n\n{reusable_sql_context}"
            return SystemMessage(content=content)
        except Exception:
            pass  # Fall through to legacy path

    parts = ["### DBFox Current State Context"]

    # 1. Follow-up Context
    follow_up = state.get("follow_up_context")
    if follow_up:
        parts.append(f"- **Follow-up Context**: {follow_up}")

    # 2. Workspace Context
    workspace = state.get("workspace_context")
    if workspace:
        parts.append(f"- **Workspace Context**: {workspace}")

    # 3. Environment Profile
    env_profile = state.get("environment_profile")
    if env_profile:
        if isinstance(env_profile, dict):
            parts.append(
                f"- **Environment**: dialect={env_profile.get('dialect')}, "
                f"env={env_profile.get('env')}, "
                f"catalog={env_profile.get('catalog_status')}, "
                f"tables={env_profile.get('table_count')}"
            )
            warnings = env_profile.get("warnings") or []
            if warnings:
                parts.append(f"  - Warnings: {'; '.join(str(w) for w in warnings[:5])}")

    # 4. Semantic Resolution
    sem_res = state.get("semantic_resolution")
    if sem_res and isinstance(sem_res, dict):
        sem_text = sem_res.get("semantic_context_text", "")
        if sem_text:
            parts.append(f"- **Semantic Context**: {sem_text}")

    # 5. Schema Context
    schema = state.get("schema_context")
    if schema:
        tables = schema.get("selected_tables") if isinstance(schema, dict) else None
        if tables:
            parts.append(f"- **Selected Schema Tables**: {', '.join(tables)}")
        raw_schema = schema.get("schema_context") if isinstance(schema, dict) else None
        if raw_schema:
            parts.append(f"- **Schema Context DDL snippet**:\n```sql\n{raw_schema[:3000]}\n```")

    # 5. Query Plan
    query_plan = state.get("query_plan")
    if query_plan:
        parts.append(f"- **Structured Query Plan**:\n```json\n{query_plan}\n```")

    # 6. SQL candidate
    sql = state.get("sql")
    if sql:
        parts.append(f"- **Current SQL Candidate**:\n```sql\n{sql}\n```")

    # 7. Safety check (validate result)
    safety = state.get("safety")
    if safety:
        parts.append(
            f"- **SQL Safety & TrustGate Result**: "
            f"can_execute={safety.get('can_execute')}, "
            f"passed={safety.get('passed')}, "
            f"requires_confirmation={safety.get('requires_confirmation')}"
        )
        if safety.get("blocked_reasons"):
            parts.append(f"  - Blocked Reasons: {safety.get('blocked_reasons')}")
        if safety.get("messages"):
            parts.append(f"  - Safety Messages: {safety.get('messages')}")

    # 8. Query Execution
    execution = state.get("execution")
    if execution:
        success = execution.get("success")
        parts.append(f"- **Query Execution Status**: success={success}")
        if success:
            parts.append(f"  - Rows returned: {execution.get('rowCount')}")
            rows = execution.get("rows")
            if rows:
                parts.append(f"  - Sample rows:\n```json\n{rows[:5]}\n```")
        else:
            parts.append(f"  - Execution Error: {execution.get('error')}")

    # 10. Errors
    error = state.get("error")
    if error:
        parts.append(f"- **Runtime Error Warning**: {error}")

    memory_context = _format_conversation_memory(state)
    if memory_context:
        parts.append(memory_context)

    reusable_sql_context = _format_reusable_sql_candidates(state)
    if reusable_sql_context:
        parts.append(reusable_sql_context)

    content = "\n\n".join(parts)
    return SystemMessage(content=content)
