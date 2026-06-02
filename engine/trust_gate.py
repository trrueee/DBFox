from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from engine.guardrail import GuardrailResult, guardrail_check
from engine.models import DataSource


RiskLevel = Literal["safe", "warning", "danger"]
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
    original_sql: str
    safe_sql: str | None
    passed: bool
    can_execute: bool
    requires_confirmation: bool
    guardrail: GuardrailResult
    schema_warnings: list[str] = Field(default_factory=list)
    scope_state: dict[str, Any] = Field(default_factory=dict)
    messages: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrustGate:
    """Schema and safety gate for AI-generated SQL."""

    def __init__(self, db: Session, schema_validator: SchemaValidator) -> None:
        self.db = db
        self.schema_validator = schema_validator

    def evaluate(self, datasource_id: str, sql: str) -> TrustGateResult:
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

        requires_confirmation = risk_level == "warning"
        if env == "prod":
            requires_confirmation = True
            messages.append("Production datasource requires manual confirmation.")

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

    def execution_decision(self, datasource_id: str, sql: str) -> ExecutionSafetyDecision:
        datasource = self.db.query(DataSource).filter(DataSource.id == datasource_id).first()
        trust_gate = self.evaluate(datasource_id, sql)
        guardrail = trust_gate["guardrail"]
        schema_warnings = list(trust_gate.get("schemaWarnings", []))
        messages = list(trust_gate.get("messages", []))
        env = str(datasource.env or "dev").lower() if datasource else "unknown"
        guardrail_rejected = guardrail.get("result") == "reject"
        requires_confirmation = env == "prod"
        if schema_warnings:
            messages.append("Execution blocked until schema validation warnings are resolved.")
        if requires_confirmation:
            messages.append("Execution blocked until production datasource confirmation is handled.")

        can_execute = bool(
            datasource
            and not guardrail_rejected
            and not schema_warnings
            and not requires_confirmation
        )
        safe_sql = str(guardrail.get("safeSql") or "").strip() if can_execute else None

        return ExecutionSafetyDecision(
            datasource_id=datasource_id,
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
            messages=messages,
        )
