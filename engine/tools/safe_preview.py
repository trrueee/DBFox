from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from engine.tools.db.preview import db_preview as _db_preview


def db_preview(db: Session, datasource_id: str, *, table: str, columns: list[str] | None = None,
               limit: int = 10, where: dict[str, Any] | None = None,
               order_by: dict[str, Any] | list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Guard db.preview against raw SQL fragment injection.

    The underlying SQL builder only accepts structured params:
    - where:  {"column": "status", "op": "=", "value": "active"}
    - order_by: {"column": "id", "direction": "desc"} or [{...}]
    """
    if isinstance(where, str) and where.strip():
        raise ValueError(
            "Raw string WHERE fragments are not allowed. "
            "Use structured where: {column, op, value}."
        )
    if isinstance(order_by, str) and order_by.strip():
        raise ValueError(
            "Raw string ORDER BY fragments are not allowed. "
            "Use structured order_by: {column, direction} or [{...}]."
        )

    # This wrapper validates and delegates to the real preview handler.
    # The old ToolContext/ToolObservation bridge is kept here since db_preview
    # internally still uses those types.
    from engine.tools.runtime.context import ToolContext
    from engine.agent_core.types import ToolObservation
    from engine.agent_core.types import AgentRunRequest

    args: dict[str, Any] = {"table": table, "limit": limit}
    if columns:
        args["columns"] = columns
    if where:
        args["where"] = where
    if order_by:
        args["order_by"] = order_by

    ctx = ToolContext(
        db=db,
        request=AgentRunRequest(datasource_id=datasource_id, question=""),
        state_view={"datasource_id": datasource_id},
    )

    result: ToolObservation = _db_preview(ctx, args)
    if result.status != "success":
        raise RuntimeError(result.error or "db.preview failed")
    return result.output or {}
