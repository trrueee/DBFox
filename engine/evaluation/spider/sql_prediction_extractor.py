from __future__ import annotations

from typing import Any


def extract_final_sql(response: Any, events: list[dict[str, Any]]) -> str | None:
    """Extract the single final predicted SQL from a DataBox agent run.

    Priority:
      1. Last sql.validate safe_sql from events
      2. response.sql
      3. Last sql.generate sql from events
    """
    candidates: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            sql = value.strip()
            if sql:
                candidates.append(sql)

    # 1. Validated safe_sql from events (preferred).
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        step_name = str(step.get("name") or "")
        tool_name = str(step.get("tool_name") or "")
        if step_name == "validate_sql" or tool_name == "sql.validate":
            add(step.get("safe_sql"))
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("safe_sql"))
    if candidates:
        return candidates[-1]

    # 2. Response-level SQL.
    add(getattr(response, "sql", None))
    if candidates:
        return candidates[-1]

    # 3. Generated SQL from events.
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        step_name = str(step.get("name") or "")
        tool_name = str(step.get("tool_name") or "")
        if step_name == "generate_sql_candidate" or tool_name == "sql.generate":
            add(step.get("sql"))
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("sql"))
    return candidates[-1] if candidates else None
