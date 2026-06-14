"""Clarification policy — coding-agent style: explore first, ask only when necessary."""

from __future__ import annotations


def should_progress_clarify(
    *,
    failure_layer: str | None,
    root_cause: str | None,
    progress_status: str,
) -> bool:
    """Gate progress-node clarify decisions against the same policy."""
    if progress_status != "clarify":
        return True

    combined = f"{failure_layer or ''} {root_cause or ''}".lower()
    if _mentions_self_recoverable(combined):
        return False
    if failure_layer in ("schema", "sql_generation", "sql_validation", "execution", "result_analysis"):
        return False
    if failure_layer == "semantic":
        return True
    return True


def _mentions_self_recoverable(text: str) -> bool:
    markers = (
        "table name", "table not found", "unknown table", "which table",
        "column", "field name", "unknown column", "not found",
        "sql error", "syntax error", "execute", "query failed",
        "empty result", "no rows", "no data",
        "join path", "how to join", "relationship",
        "should i query", "do you want me to", "shall i",
    )
    return any(m in text for m in markers)
