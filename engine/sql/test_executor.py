"""Test-only executor helper that allows guardrail bypass.

This module provides ``execute_query_for_test`` which resolves safety with
``bypass_guardrail=True`` and then delegates to the shared
``_run_approved_query`` helper in ``executor.py`` — the same execution path
used by the production ``execute_query``.  This file is intentionally
separated from the public executor so that production code paths can never
accidentally pass ``bypass_guardrail=True``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from engine.sql.executor import (
    _decision_checks_for_error,
    _decision_checks_for_history,
    _decision_block_message,
    _resolve_execution_safety_decision,
    _run_approved_query,
    guardrail_bypass_allowed,
)
from engine.errors import GuardrailValidationError
from engine.models import DataSource
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision

logger = logging.getLogger("dbfox.sql.executor.test")


def execute_query_for_test(
    db: Session,
    datasource_id: str,
    sql_str: str,
    question: str | None = None,
    execution_id: str | None = None,
    safety_decision: ExecutionSafetyDecision | dict[str, Any] | None = None,
    safety_policy: ExecutionPolicy = "readonly",
) -> dict[str, Any]:
    """Execute a query with guardrail bypass enabled.

    This is the **only** sanctioned way to bypass guardrails and is intended
    exclusively for test code.  It:

    1. Checks ``guardrail_bypass_allowed()`` (requires ``DBFOX_TESTING=1``
       and ``DBFOX_ALLOW_GUARDRAIL_BYPASS=1``; always denied in frozen
       builds).
    2. Logs a warning when bypass is used.
    3. Resolves the safety decision with ``bypass_guardrail=True``.
    4. Delegates to the shared ``_run_approved_query`` for execution and
       history recording (same code path as ``execute_query``).

    Raises ``GuardrailValidationError`` if bypass is not allowed or if the
    safety decision blocks execution.
    """
    if not guardrail_bypass_allowed():
        raise GuardrailValidationError(
            "Guardrail bypass is only available in the test environment.",
            checks=[{
                "rule": "trust_gate_bypass_disabled",
                "level": "reject",
                "message": "bypass_guardrail requires DBFOX_TESTING=1 and DBFOX_ALLOW_GUARDRAIL_BYPASS=1.",
            }],
        )

    logger.warning(
        "Guardrail bypass requested via execute_query_for_test — "
        "datasource=%s env gates satisfied.",
        datasource_id,
    )

    decision = _resolve_execution_safety_decision(
        db=db,
        datasource_id=datasource_id,
        sql_str=sql_str,
        bypass_guardrail=True,
        safety_decision=safety_decision,
        policy=safety_policy,
    )

    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise ValueError("Data source not found")

    execution_id = execution_id or f"exec-test-{uuid.uuid4()}"
    guard_checks_json = json.dumps(_decision_checks_for_history(decision), ensure_ascii=False)
    guard_res = decision.guardrail

    if not decision.can_execute or not str(decision.safe_sql or "").strip():
        raise GuardrailValidationError(
            _decision_block_message(decision),
            checks=_decision_checks_for_error(decision),
        )

    safe_sql = str(decision.safe_sql or "").strip()
    result = _run_approved_query(
        db=db,
        ds=ds,
        datasource_id=datasource_id,
        safe_sql=safe_sql,
        sql_str=sql_str,
        question=question,
        execution_id=execution_id,
        guard_res=guard_res,
        guardrail_ms=0,  # test helper doesn't profile guardrail separately
        guard_checks_json=guard_checks_json,
    )
    result["safetyDecision"] = decision.model_dump(mode="json")
    return result
