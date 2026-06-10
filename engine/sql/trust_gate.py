from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from engine.sql.guardrail import GuardrailResult, guardrail_check
from engine.models import DataSource
from engine.sql.dry_run import dry_run_query


RiskLevel = Literal["safe", "warning", "danger"]
ExecutionPolicy = Literal[
    "readonly",
    "user_readonly",
    "agent_readonly",
    "table_preview",
    "schema_introspection",
    "explain",
    "export",
]
SchemaValidator = Callable[[str, Session, str], list[str]]


class TrustGateResult(TypedDict, total=False):
    sql: str
    schemaWarnings: list[str]
    guardrail: GuardrailResult
    riskLevel: RiskLevel
    requiresConfirmation: bool
    messages: list[str]
    canExecute: bool


class ExecutionSafetyDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"safety-{uuid4()}")
    datasource_id: str
    policy: ExecutionPolicy = "readonly"
    original_sql: str
    safe_sql: str | None
    passed: bool
    can_execute: bool
    requires_confirmation: bool
    guardrail: GuardrailResult
    schema_warnings: list[str] = Field(default_factory=list)
    scope_state: dict[str, Any] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrustGate:
    """Schema and safety gate for AI-generated SQL."""

    def __init__(self, db: Session, schema_validator: SchemaValidator) -> None:
        self.db = db
        self.schema_validator = schema_validator

    def evaluate(self, datasource_id: str, sql: str, policy: ExecutionPolicy = "readonly") -> TrustGateResult:
        datasource = self.db.query(DataSource).filter(DataSource.id == datasource_id).first()
        dialect = str(datasource.db_type or "mysql") if datasource else "mysql"
        env = str(datasource.env or "dev").lower() if datasource else "dev"

        schema_warnings = self.schema_validator(sql, self.db, datasource_id)
        guardrail = guardrail_check(sql, dialect=dialect)
        messages: list[str] = []

        guardrail_result = guardrail["result"]
        if guardrail_result == "reject":
            risk_level: RiskLevel = "danger"
            messages.append("Guardrail rejected this SQL. Execution is blocked.")
        elif schema_warnings or guardrail_result == "warn":
            risk_level = "warning"
            if schema_warnings:
                messages.append("Schema validation found unknown tables or columns.")
            if guardrail_result == "warn":
                messages.append(guardrail["message"])
        else:
            risk_level = "safe"
            messages.append("SQL passed schema validation and guardrail checks.")

        requires_confirmation = _requires_confirmation(
            env=env, policy=policy, risk_level=risk_level,
        )
        if requires_confirmation:
            if env == "prod":
                messages.append("Production datasource agent execution requires manual confirmation.")
            else:
                messages.append("Execution requires manual confirmation.")

        can_execute = guardrail_result != "reject"

        return {
            "sql": sql,
            "schemaWarnings": schema_warnings,
            "guardrail": guardrail,
            "riskLevel": risk_level,
            "requiresConfirmation": requires_confirmation,
            "messages": messages,
            "canExecute": can_execute,
        }

    def execution_decision(
        self,
        datasource_id: str,
        sql: str,
        policy: ExecutionPolicy = "readonly",
    ) -> ExecutionSafetyDecision:
        datasource = self.db.query(DataSource).filter(DataSource.id == datasource_id).first()
        trust_gate = self.evaluate(datasource_id, sql, policy=policy)
        guardrail = trust_gate["guardrail"]
        schema_warnings = list(trust_gate.get("schemaWarnings", []))
        messages = list(trust_gate.get("messages", []))
        env = str(datasource.env or "dev").lower() if datasource else "unknown"
        guardrail_rejected = guardrail.get("result") == "reject"
        guardrail_checks = list(guardrail.get("checks", []))
        candidate_safe_sql = str(guardrail.get("safeSql") or "").strip()
        select_star_blocked = (
            policy == "agent_readonly"
            and any(check.get("rule") == "select_star" for check in guardrail_checks)
        )
        requires_confirmation = _requires_confirmation(
            env=env, policy=policy, risk_level=trust_gate["riskLevel"],
        )
        blocked_reasons: list[str] = []

        if not datasource:
            blocked_reasons.append("datasource_scope")
            messages.append("Datasource scope could not be resolved.")
        if guardrail_rejected:
            blocked_reasons.append("guardrail_reject")
        elif not candidate_safe_sql:
            blocked_reasons.append("safe_sql_missing")
            messages.append("Guardrail did not produce safe_sql. Execution is blocked.")
        if schema_warnings:
            blocked_reasons.append("schema_validation")
            messages.append("Execution blocked until schema validation warnings are resolved.")
        if requires_confirmation:
            blocked_reasons.append("requires_confirmation")
            messages.append("Execution blocked until production datasource confirmation is handled.")
        if select_star_blocked:
            blocked_reasons.append("select_star")
            messages.append("Agent execution requires explicit projected columns instead of SELECT *.")

        if (
            datasource
            and not guardrail_rejected
            and candidate_safe_sql
            and _should_dry_run(candidate_safe_sql)
        ):
            try:
                dry_run = dry_run_query(self.db, datasource_id, candidate_safe_sql)
            except Exception as exc:
                dry_run = None
                blocked_reasons.append("explain_unavailable")
                messages.append(f"EXPLAIN dry-run unavailable for safe_sql: {exc}")
            if dry_run is not None and dry_run.ok:
                messages.append("EXPLAIN dry-run validated safe_sql.")
            elif dry_run is not None:
                reason = dry_run.blocked_reason or "explain_unavailable"
                blocked_reasons.append(reason)
                if dry_run.message:
                    messages.append(f"EXPLAIN dry-run failed for safe_sql: {dry_run.message}")

        blocked_reasons = list(dict.fromkeys(blocked_reasons))
        can_execute = not blocked_reasons
        safe_sql = candidate_safe_sql if can_execute else None

        return ExecutionSafetyDecision(
            datasource_id=datasource_id,
            policy=policy,
            original_sql=sql,
            safe_sql=safe_sql,
            passed=can_execute,
            can_execute=can_execute,
            requires_confirmation=requires_confirmation,
            guardrail=guardrail,
            schema_warnings=schema_warnings,
            scope_state={
                "datasource_exists": bool(datasource),
                "datasource_id": datasource_id,
                "db_type": str(datasource.db_type or "mysql") if datasource else None,
                "env": env,
                "is_read_only": bool(datasource.is_read_only) if datasource else None,
                "project_id": str(datasource.project_id) if datasource and datasource.project_id else None,
                "environment_id": str(datasource.environment_id) if datasource and datasource.environment_id else None,
            },
            blocked_reasons=blocked_reasons,
            messages=messages,
        )


def _requires_confirmation(
    *,
    env: str,
    policy: ExecutionPolicy,
    risk_level: RiskLevel,
) -> bool:
    """Determine whether human confirmation is required.

    Key principle: prod ≠ blocked.  The decision depends on WHO is
    executing (user vs agent) and WHAT they are doing (browsing vs
    generating SQL autonomously).
    """
    # Non-intrusive operations — never require confirmation
    if policy in {"table_preview", "schema_introspection", "explain"}:
        return False

    # User manually executing their own SQL — allow with guardrail
    if policy == "user_readonly":
        return False

    # Agent autonomously executing SQL — stricter
    if policy == "agent_readonly":
        return env == "prod" or risk_level == "warning"

    # Export — allowed (export of existing result, not re-execution)
    if policy == "export":
        return False

    # Legacy / fallback — danger is blocked, not confirmed
    return False


def _should_dry_run(sql: str) -> bool:
    normalized = sql.strip().lstrip("(").upper()
    return normalized.startswith("SELECT") or normalized.startswith("WITH")
