from __future__ import annotations

from typing import Any
from langchain_core.messages import SystemMessage


def build_context_message(state: dict[str, Any]) -> SystemMessage:
    """Format the factual DataBox business state variables into a SystemMessage context block.

    This ensures the LLM stays grounded in actual tool output and execution history.
    """
    parts = ["### DataBox Current State Context"]

    # 1. Follow-up Context
    follow_up = state.get("follow_up_context")
    if follow_up:
        parts.append(f"- **Follow-up Context**: {follow_up}")

    # 2. Workspace Context
    workspace = state.get("workspace_context")
    if workspace:
        parts.append(f"- **Workspace Context**: {workspace}")

    # 3. Schema Context
    schema = state.get("schema_context")
    if schema:
        tables = schema.get("selected_tables") if isinstance(schema, dict) else None
        if tables:
            parts.append(f"- **Selected Schema Tables**: {', '.join(tables)}")
        raw_schema = schema.get("schema_context") if isinstance(schema, dict) else None
        if raw_schema:
            parts.append(f"- **Schema Context DDL snippet**:\n```sql\n{raw_schema[:3000]}\n```")

    # 4. Query Plan
    query_plan = state.get("query_plan")
    if query_plan:
        parts.append(f"- **Structured Query Plan**:\n```json\n{query_plan}\n```")

    # 5. SQL candidate
    sql = state.get("sql")
    if sql:
        parts.append(f"- **Current SQL Candidate**:\n```sql\n{sql}\n```")

    # 6. Safety check (validate result)
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

    # 7. Query Execution
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

    # 8. Profile result
    profile = state.get("result_profile")
    if profile:
        parts.append(f"- **Result Profile**:\n```json\n{profile}\n```")

    # 9. Errors
    error = state.get("error")
    if error:
        parts.append(f"- **Runtime Error Warning**: {error}")

    content = "\n\n".join(parts)
    return SystemMessage(content=content)
