from __future__ import annotations

from typing import Any


def extract_final_sql(response: Any, events: list[dict[str, Any]]) -> str | None:
    """Extract the single final predicted SQL from a DBFox agent run.

    Priority:
      1. Last sql.execute_readonly safe_sql from events
      2. Last sql.validate safe_sql from events
      3. response.sql
      4. Last model.sql_draft sql from events
    """
    candidates: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            sql = value.strip()
            if sql:
                candidates.append(sql)

    # 1. sql.execute_readonly safe_sql from events (preferred).
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "")
        if tool_name == "sql.execute_readonly":
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("safe_sql"))
    if candidates:
        return candidates[-1]

    # 2. sql.validate safe_sql from events.
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "")
        if tool_name == "sql.validate":
            add(step.get("safe_sql"))
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("safe_sql"))
    if candidates:
        return candidates[-1]

    # 3. Response-level SQL.
    add(getattr(response, "sql", None))
    if candidates:
        return candidates[-1]

    # 4. Model-drafted SQL from events.
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "")
        if tool_name == "model.sql_draft":
            add(step.get("sql"))
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("sql") or output.get("safe_sql"))
    return candidates[-1] if candidates else None
