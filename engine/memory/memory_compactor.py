"""Compaction strategies to keep short-term memory within context limits."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class MemoryCompactionConfig(BaseModel):
    max_messages: int = 30
    max_tool_messages: int = 12
    max_schema_chars: int = 4000
    max_execution_sample_rows: int = 5
    summarize_after_messages: int = 40


DEFAULT_CONFIG = MemoryCompactionConfig()


def compact_messages(messages: list[Any], config: MemoryCompactionConfig | None = None) -> list[Any]:
    """Trim messages to fit within context budget.

    Strategy:
      1. Keep all non-tool messages.
      2. Keep most recent N tool messages (capped by ``max_tool_messages``).
      3. If still over budget, drop oldest messages from the head.
    """
    cfg = config or DEFAULT_CONFIG
    if not messages or len(messages) <= cfg.max_messages:
        return list(messages)

    # Split
    tool_msgs = [m for m in messages if _is_tool(m)]
    other_msgs = [m for m in messages if not _is_tool(m)]

    # Keep last N tool messages.  Guard against max_tool_messages=0
    # because ``list[-0:]`` returns the *entire* list in Python.
    if cfg.max_tool_messages <= 0:
        kept_tools: list[Any] = []
    elif len(tool_msgs) > cfg.max_tool_messages:
        kept_tools = tool_msgs[-cfg.max_tool_messages:]
    else:
        kept_tools = tool_msgs

    # Rebuild preserving original order: non-tool messages first, then tool
    # messages.  Both groups maintain their relative order.
    result = other_msgs + kept_tools
    if len(result) > cfg.max_messages:
        # Drop oldest entries (from the head) to stay within budget.
        result = result[-cfg.max_messages:]

    return result


def compact_schema_context(schema_text: str, config: MemoryCompactionConfig | None = None) -> str:
    """Truncate schema context to fit budget."""
    cfg = config or DEFAULT_CONFIG
    if len(schema_text) <= cfg.max_schema_chars:
        return schema_text
    return schema_text[:cfg.max_schema_chars] + "\n... (schema truncated)"


def compact_execution_result(execution: dict[str, Any] | None, config: MemoryCompactionConfig | None = None) -> dict[str, Any] | None:
    """Truncate execution result rows to a sample."""
    if not execution:
        return None
    cfg = config or DEFAULT_CONFIG
    rows = execution.get("rows") or []
    if isinstance(rows, list) and len(rows) > cfg.max_execution_sample_rows:
        execution = dict(execution)
        execution["rows"] = rows[:cfg.max_execution_sample_rows]
        execution["_truncated"] = True
        execution["_original_row_count"] = len(rows)
    return execution


def _is_tool(msg: Any) -> bool:
    name = type(msg).__name__
    return "Tool" in name or "ToolMessage" in name
