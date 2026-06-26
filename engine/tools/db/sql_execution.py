"""sql.validate and sql.execute_readonly tool handlers."""

from __future__ import annotations

import time
from typing import Any
from sqlalchemy.orm import Session
from engine.sql.dialect_context import DialectContext
from engine.sql.executor import execute_query
from engine.sql.safety.service import SqlSafetyService
from engine.tools.db.preview import _infer_column_types


def sql_validate(db: Session, datasource_id: str, sql: str, question: str = "") -> dict[str, Any]:
    """Validate a SELECT SQL query against safety policies, schema cache, and syntax check, without executing it."""
    sql = sql.strip()
    if not sql:
        raise ValueError("sql is required.")

    ctx = DialectContext.from_datasource_id(db, datasource_id)
    decision = SqlSafetyService(db).build_execution_decision(sql, ctx, policy="agent_readonly")

    return {
        "can_execute": decision.can_execute,
        "requires_confirmation": decision.requires_confirmation,
        "safe_sql": decision.safe_sql,
        "original_sql": decision.original_sql,
        "risk_level": decision.risk_level,
        "blocked_reasons": decision.blocked_reasons,
        "messages": decision.messages,
        "execution_safety_decision": decision.model_dump(mode="json"),
    }


def sql_execute_readonly(
    db: Session,
    datasource_id: str,
    sql: str | None = None,
    question: str = "",
    safety: dict[str, Any] | None = None,
    ignored_model_sql: str | None = None,
) -> dict[str, Any]:
    """Execute a read-only SELECT SQL statement using the pre-validated safety decision."""
    start = time.perf_counter()
    if not safety:
        raise RuntimeError("SQL execution requires a previous successful sql.validate result.")

    original_sql = str(safety.get("original_sql") or "").strip()
    safe_sql = str(safety.get("safe_sql") or "").strip()
    ignored_sql = str(ignored_model_sql or sql or "").strip() or None

    blocked_reasons = list(safety.get("blocked_reasons") or [])
    hard_blockers = [r for r in blocked_reasons if r != "requires_confirmation"]
    if hard_blockers:
        raise RuntimeError(f"SQL execution is blocked by safety rules: {hard_blockers}")

    if not bool(safety.get("can_execute")) or not safe_sql:
        raise RuntimeError("SQL execution requires a previous successful sql.validate result.")

    if safety.get("requires_confirmation"):
        raise RuntimeError("SQL execution requires manual approval.")

    result = execute_query(
        db,
        datasource_id,
        safe_sql,
        question=question,
        safety_decision=safety,
        safety_policy="agent_readonly",
        redact=True,
    )

    rows = result.get("rows") or []

    return {
        "status": "success",
        "success": True,
        "rowCount": len(rows),
        "columns": result.get("columns") or [],
        "column_types": _infer_column_types(result),
        "returned_rows": len(rows),
        "truncated": bool(result.get("truncated")),
        "rows": rows,
        "safe_sql": safe_sql,
        "execution_time_ms": result.get("latencyMs", 0),
        "explain_plan": result.get("explainPlan"),
        "warnings": result.get("warnings") or [],
        "audit": {
            "readonly_checked": True,
            "limit_injected": original_sql != safe_sql and "LIMIT" in safe_sql.upper(),
            "guardrail_result": (result.get("guardrail") or {}).get("result"),
            "trust_gate": True,
            "executed_sql_source": "state.safety.safe_sql",
            "ignored_model_sql": ignored_sql,
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }
