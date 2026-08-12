"""sql_validate and sql_execute_readonly tool handlers."""

from __future__ import annotations

import time
from typing import Any
from sqlalchemy.orm import Session

from engine.errors import GuardrailValidationError, ToolInputError
from engine.policy.authority import ExecutionAuthority
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
    question: str = "",
    safety: dict[str, Any] | None = None,
    execution_id: str | None = None,
    expected_connection_generation: int | None = None,
    execution_authority: ExecutionAuthority | None = None,
) -> dict[str, Any]:
    """Execute a read-only SELECT SQL statement using the pre-validated safety decision."""
    start = time.perf_counter()
    if not safety:
        raise ToolInputError(
            "Run sql_validate successfully before calling sql_execute_readonly."
        )

    original_sql = str(safety.get("original_sql") or "").strip()
    safe_sql = str(safety.get("safe_sql") or "").strip()

    blocked_reasons = list(safety.get("blocked_reasons") or [])
    hard_blockers = [r for r in blocked_reasons if r != "requires_confirmation"]
    if hard_blockers:
        raise GuardrailValidationError(
            "SQL execution was blocked by the validated safety decision.",
            checks=[
                {
                    "rule": str(reason),
                    "level": "reject",
                    "message": "The validated SQL safety decision blocks execution.",
                }
                for reason in hard_blockers
            ],
        )

    if not bool(safety.get("can_execute")) or not safe_sql:
        raise ToolInputError(
            "The sql_validate result is not executable; correct the SQL and validate it again."
        )

    approval_granted = bool(
        execution_authority
        and execution_authority.authorizes_safety(
            tool_name="sql_execute_readonly",
            safety=safety,
            datasource_generation=expected_connection_generation,
        )
    )
    if safety.get("requires_confirmation") and not approval_granted:
        raise GuardrailValidationError(
            "SQL execution requires approval through the Agent approval workflow.",
            checks=[{
                "rule": "requires_confirmation",
                "level": "reject",
                "message": "Execution authority was not present.",
            }],
        )

    result = execute_query(
        db,
        datasource_id,
        safe_sql,
        question=question,
        safety_decision=safety,
        safety_policy="agent_readonly",
        redact=True,
        execution_id=execution_id,
        expected_connection_generation=expected_connection_generation,
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
            "executed_sql_source": "validated_sql_artifact.safeSql",
            "history_id": result.get("historyId"),
            "execution_id": result.get("executionId"),
        },
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }
