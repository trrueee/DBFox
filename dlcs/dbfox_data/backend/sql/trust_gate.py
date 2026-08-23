"""Pure SQL safety decision orchestration for the Data capability."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, TypedDict, cast

from dbfox_dlc_api import log_extension_exception
from sqlglot import exp

from .bound_parameters import parameter_fingerprint
from .dry_run_contracts import DryRunResult
from .guardrail import GuardrailResult, guardrail_check_with_ast
from .safety_contracts import (
    DatabaseSafetyScope,
    ExecutionPolicy,
    ExecutionSafetyDecision,
    RiskLevel,
    is_auto_limit_only_warning,
    requires_human_confirmation,
)

logger = logging.getLogger(__name__)

SchemaValidator = Callable[[str | exp.Expression], list[str]]
DryRunValidator = Callable[[str, Mapping[str, Any] | None], DryRunResult]


class TrustGateResult(TypedDict, total=False):
    sql: str
    schemaWarnings: list[str]
    guardrail: GuardrailResult
    riskLevel: RiskLevel
    requiresConfirmation: bool
    messages: list[str]
    canExecute: bool


def _public_guardrail_result(guardrail: Mapping[str, Any]) -> GuardrailResult:
    """Strip internal parser artifacts before persistence or API exposure."""

    return cast(
        GuardrailResult,
        {key: value for key, value in guardrail.items() if not key.startswith("_")},
    )


class TrustGate:
    """Evaluate SQL from immutable resource facts and explicit boundary calls."""

    def __init__(
        self,
        schema_validator: SchemaValidator,
        dry_run_validator: DryRunValidator | None = None,
    ) -> None:
        self.schema_validator = schema_validator
        self.dry_run_validator = dry_run_validator

    def evaluate(
        self,
        scope: DatabaseSafetyScope,
        sql: str,
        policy: ExecutionPolicy = "readonly",
    ) -> TrustGateResult:
        guardrail, parsed_ast = guardrail_check_with_ast(sql, dialect=scope.dialect)
        schema_warnings = self.schema_validator(
            parsed_ast if isinstance(parsed_ast, exp.Expression) else sql
        )
        public_guardrail = _public_guardrail_result(guardrail)
        messages: list[str] = []

        guardrail_result = public_guardrail["result"]
        benign_auto_limit_warning = (
            is_auto_limit_only_warning(public_guardrail) and not schema_warnings
        )
        if guardrail_result == "reject":
            risk_level: RiskLevel = "danger"
            messages.append("Guardrail rejected this SQL. Execution is blocked.")
        elif schema_warnings or (guardrail_result == "warn" and not benign_auto_limit_warning):
            risk_level = "warning"
            if schema_warnings:
                messages.append("Schema validation found unknown tables or columns.")
            if guardrail_result == "warn":
                messages.append(public_guardrail["message"])
        else:
            risk_level = "safe"
            messages.append(
                public_guardrail["message"]
                if guardrail_result == "warn"
                else "SQL passed schema validation and guardrail checks."
            )

        requires_confirmation = requires_human_confirmation(
            env=scope.environment,
            policy=policy,
            risk_level=risk_level,
        )
        if requires_confirmation:
            messages.append(
                "Production database agent execution requires manual confirmation."
                if scope.environment == "prod"
                else "Execution requires manual confirmation."
            )

        return {
            "sql": sql,
            "schemaWarnings": schema_warnings,
            "guardrail": public_guardrail,
            "riskLevel": risk_level,
            "requiresConfirmation": requires_confirmation,
            "messages": messages,
            "canExecute": guardrail_result != "reject",
        }

    def execution_decision(
        self,
        scope: DatabaseSafetyScope,
        sql: str,
        policy: ExecutionPolicy = "readonly",
        parameters: Mapping[str, Any] | None = None,
    ) -> ExecutionSafetyDecision:
        trust_gate = self.evaluate(scope, sql, policy=policy)
        guardrail = trust_gate["guardrail"]
        schema_warnings = list(trust_gate.get("schemaWarnings", []))
        messages = list(trust_gate.get("messages", []))
        guardrail_rejected = guardrail.get("result") == "reject"
        guardrail_checks = list(guardrail.get("checks", []))
        candidate_safe_sql = str(guardrail.get("safeSql") or "").strip()
        select_star_blocked = (
            policy == "agent_readonly"
            and any(check.get("rule") == "select_star" for check in guardrail_checks)
        )
        requires_confirmation = bool(trust_gate["requiresConfirmation"])
        blocked_reasons: list[str] = []

        if not scope.exists:
            blocked_reasons.append("datasource_scope")
            messages.append("Database resource scope could not be resolved.")
        if guardrail_rejected:
            blocked_reasons.append("guardrail_reject")
        elif not candidate_safe_sql:
            blocked_reasons.append("safe_sql_missing")
            messages.append("Guardrail did not produce safe_sql. Execution is blocked.")
        if schema_warnings:
            messages.append("Schema validation warning: unknown tables or columns in query.")
        if requires_confirmation:
            messages.append("Execution requires manual approval before running.")
        if select_star_blocked:
            blocked_reasons.append("select_star")
            messages.append("Agent execution requires explicit projected columns instead of SELECT *.")

        if (
            scope.exists
            and not guardrail_rejected
            and candidate_safe_sql
            and self.dry_run_validator is not None
        ):
            try:
                dry_run = self.dry_run_validator(candidate_safe_sql, parameters)
            except Exception as exc:
                log_extension_exception(
                    logger,
                    operation="dbfox.data.sql.dry_run",
                    exc=exc,
                    fingerprint_subject=scope.resource_id,
                )
                dry_run = None
                messages.append("EXPLAIN dry-run warning (execution allowed): validation unavailable.")

            if dry_run is not None:
                if dry_run.ok:
                    messages.append("EXPLAIN dry-run validated safe_sql.")
                elif dry_run.blocked_reason in ("syntax_error", "schema_error"):
                    blocked_reasons.append(dry_run.blocked_reason)
                    messages.append(
                        f"EXPLAIN dry-run failed ({dry_run.blocked_reason}): {dry_run.message}"
                    )
                else:
                    messages.append(
                        f"EXPLAIN dry-run warning (execution allowed): {dry_run.message}"
                    )

        blocked_reasons = list(dict.fromkeys(blocked_reasons))
        can_execute = not blocked_reasons

        return ExecutionSafetyDecision(
            datasource_id=scope.resource_id,
            policy=policy,
            original_sql=sql,
            safe_sql=candidate_safe_sql if can_execute else None,
            passed=can_execute,
            can_execute=can_execute,
            requires_confirmation=requires_confirmation,
            risk_level=trust_gate["riskLevel"],
            guardrail=guardrail,
            schema_warnings=schema_warnings,
            scope_state={
                "datasource_exists": scope.exists,
                "datasource_id": scope.resource_id,
                "db_type": scope.dialect if scope.exists else None,
                "env": scope.environment,
                "is_read_only": scope.is_read_only,
                "project_id": scope.project_id,
            },
            blocked_reasons=blocked_reasons,
            messages=messages,
            parameter_fingerprint=parameter_fingerprint(parameters),
        )
