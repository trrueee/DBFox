from __future__ import annotations

from typing import Any

from engine.agent_core.tool_registry import ToolContext
from engine.agent_core.types import ToolObservation
from engine.tools.db_tools import db_preview as _db_preview


def db_preview(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Guard db.preview against raw SQL fragment injection.

    This wrapper blocks raw WHERE/ORDER BY strings at the tool boundary.
    The underlying SQL builder only accepts structured parameters:

    - where:  {"column": "status", "op": "=", "value": "active"}
    - order_by: {"column": "id", "direction": "desc"}
      or [{"column": "name"}, {"column": "id", "direction": "desc"}]
    """
    if isinstance(args.get("where"), str) and str(args.get("where") or "").strip():
        return ToolObservation(
            name="db.preview",
            status="failed",
            input=args,
            error="Raw string WHERE fragments are not allowed. Use structured where: {column, op, value}.",
            latency_ms=0,
        )

    if isinstance(args.get("order_by"), str) and str(args.get("order_by") or "").strip():
        return ToolObservation(
            name="db.preview",
            status="failed",
            input=args,
            error="Raw string ORDER BY fragments are not allowed. Use structured order_by: {column, direction} or [{...}].",
            latency_ms=0,
        )

    return _db_preview(ctx, args)
