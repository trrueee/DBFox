from __future__ import annotations

from typing import Any


def extract_final_sql(response: Any, events: list[dict[str, Any]]) -> str | None:
    """Extract the single final predicted SQL from a DataBox agent run.

    Priority:
      1. Last db.query safe_sql from events (new ReAct path)
      2. Last sql.validate safe_sql from events (legacy)
      3. response.sql
      4. Last sql.generate / db.query sql from events
    """
    candidates: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            sql = value.strip()
            if sql:
                candidates.append(sql)

    # 1. db.query safe_sql from events (preferred).
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "")
        if tool_name == "db.query":
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("safe_sql"))
    if candidates:
        return candidates[-1]

    # 2. Legacy sql.validate safe_sql from events.
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

    # 4. Generated SQL from events.
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "")
        if tool_name in ("sql.generate", "db.query"):
            add(step.get("sql"))
            output = step.get("output")
            if isinstance(output, dict):
                add(output.get("sql") or output.get("safe_sql"))
    return candidates[-1] if candidates else None
