"""Test-only query execution with an explicitly gated guardrail bypass."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from engine.errors import GuardrailValidationError
from engine.json_codec import dumps
from engine.models import DataSource
from engine.sql.executor import (
    _decision_block_message,
    _decision_checks_for_error,
    _decision_checks_for_history,
    _resolve_execution_safety_decision,
    _run_approved_query,
)
from engine.sql.safety_gate import guardrail_bypass_allowed
from dlcs.dbfox_data.backend.sql.safety_contracts import (
    ExecutionPolicy,
    ExecutionSafetyDecision,
)


logger = logging.getLogger("dbfox.tests.support.executor")


def execute_query_for_test(
    db: Session,
    datasource_id: str,
    sql_str: str,
    question: str | None = None,
    execution_id: str | None = None,
    safety_decision: ExecutionSafetyDecision | dict[str, Any] | None = None,
    safety_policy: ExecutionPolicy = "readonly",
) -> dict[str, Any]:
    """Execute through the production path after both test-only gates pass."""

    if not guardrail_bypass_allowed():
        raise GuardrailValidationError(
            "Guardrail bypass is only available in the test environment.",
            checks=[
                {
                    "rule": "trust_gate_bypass_disabled",
                    "level": "reject",
                    "message": (
                        "bypass_guardrail requires DBFOX_TESTING=1 and "
                        "DBFOX_ALLOW_GUARDRAIL_BYPASS=1."
                    ),
                }
            ],
        )

    logger.warning(
        "Guardrail bypass requested via test support — datasource=%s.",
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
    datasource = db.get(DataSource, datasource_id)
    if datasource is None:
        raise ValueError("Data source not found")

    resolved_execution_id = execution_id or f"exec-test-{uuid.uuid4()}"
    if not decision.can_execute or not str(decision.safe_sql or "").strip():
        raise GuardrailValidationError(
            _decision_block_message(decision),
            checks=_decision_checks_for_error(decision),
        )

    result = _run_approved_query(
        db=db,
        ds=datasource,
        datasource_id=datasource_id,
        safe_sql=str(decision.safe_sql).strip(),
        sql_str=sql_str,
        question=question,
        execution_id=resolved_execution_id,
        guard_res=decision.guardrail,
        guardrail_ms=0,
        guard_checks_json=dumps(_decision_checks_for_history(decision)),
    )
    result["safetyDecision"] = decision.model_dump(mode="json")
    return result
