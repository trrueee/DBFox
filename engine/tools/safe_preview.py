from __future__ import annotations

from typing import Any

from engine.agent_core.tool_registry import ToolContext
from engine.agent_core.types import ToolObservation
from engine.tools.db_tools import db_preview as _db_preview


def db_preview(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Guard db.preview against raw SQL fragment injection.

    The underlying preview helper still supports structured filters. This wrapper
    blocks raw WHERE/ORDER BY strings at the tool boundary so the model cannot
    turn a table preview into an arbitrary cross-table SELECT fragment.
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
            error="Raw string ORDER BY fragments are not allowed in db.preview.",
            latency_ms=0,
        )

    return _db_preview(ctx, args)
