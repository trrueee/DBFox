"""db.query — execute Agent-written read-only SQL with full safety enforcement."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from engine.sql.dialect_context import DialectContext
from engine.sql.executor import execute_query
from engine.sql.safety.service import SqlSafetyService
from engine.tools.db.preview import _infer_column_types


def db_query(db: Session, datasource_id: str, sql: str, question: str = "") -> dict[str, Any]:
    """Execute Agent-written read-only SQL with full safety enforcement.

    The SQL passes through guardrail → TrustGate → dry-run → policy before execution.
    """
    start = time.perf_counter()
    sql = sql.strip()
    if not sql:
        raise ValueError("sql is required.")

    ctx = DialectContext.from_datasource_id(db, datasource_id)
    decision = SqlSafetyService(db).build_execution_decision(sql, ctx, policy="agent_readonly")
    result = execute_query(
        db,
        datasource_id,
        sql,
        question=question,
        safety_decision=decision,
        safety_policy="agent_readonly",
        redact=True,
    )

    decision = result.get("safetyDecision") or {}
    safe_sql = str(decision.get("safe_sql") or "").strip()
    rows = result.get("rows") or []

    return {
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
            "limit_injected": sql != safe_sql and "LIMIT" in safe_sql.upper(),
            "guardrail_result": (result.get("guardrail") or {}).get("result"),
            "trust_gate": True,
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }
