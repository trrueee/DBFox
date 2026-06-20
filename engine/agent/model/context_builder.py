from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage


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
            "- **Mode**: SQL repair active — use schema tools and sql.revise before asking the user."
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

    content = "\n\n".join(parts)
    return SystemMessage(content=content)
