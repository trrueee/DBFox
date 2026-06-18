"""db.query — execute Agent-written read-only SQL with full safety enforcement."""

from __future__ import annotations

import time
from typing import Any

from engine.tools.runtime.context import ToolContext
from engine.agent_core.types import ToolObservation
from engine.sql.executor import execute_query
from engine.tools.db._common import (
    _execution_failed,
    _failed,
    _limit_was_injected,
    _success,
)
from engine.tools.db.preview import _infer_column_types


def db_query(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Execute Agent-written read-only SQL with full safety enforcement.

    The SQL passes through guardrail → TrustGate → dry-run → policy
    before execution.  Agent must write its own SQL — this tool does not
    generate it.
    """
    start = time.perf_counter()
    sql = str(args.get("sql") or "").strip()
    if not sql:
        return _failed("db.query", args, "sql is required.", start)

    try:
        result = execute_query(
            ctx.db,
            ctx.request.datasource_id,
            sql,
            question=str(args.get("question") or ctx.request.question or ""),
            safety_policy="agent_readonly",
            redact=True,
        )
    except Exception as exc:
        return _execution_failed("db.query", args, exc, start)

    decision = result.get("safetyDecision") or {}
    safe_sql = str(decision.get("safe_sql") or "").strip()
    rows = result.get("rows") or []

    output = {
        "status": "success",
        "columns": result.get("columns") or [],
        "column_types": _infer_column_types(result),
        "returned_rows": len(rows),
        "truncated": bool(result.get("truncated")),
        "rows": rows,
        "safe_sql": safe_sql or sql,
        "execution_time_ms": result.get("latencyMs", 0),
        "explain_plan": result.get("explainPlan"),
        "warnings": result.get("warnings") or [],
        "audit": {
            "readonly_checked": True,
            "limit_injected": _limit_was_injected(sql, safe_sql),
            "guardrail_result": (result.get("guardrail") or {}).get("result"),
            "trust_gate": True,
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
    }
    return _success("db.query", args, output, start)
