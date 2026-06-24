from __future__ import annotations

from typing import Literal

import sqlglot
from sqlalchemy.orm import Session
from sqlglot import exp

from engine.sql.dialect_context import DialectContext
from engine.sql.guardrail import guardrail_check
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate


SqlValidationKind = Literal["user", "agent", "source_artifact", "derived", "explain"]


class SqlSafetyService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def validate_user_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx, kind="user")

    def validate_agent_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx, kind="agent")

    def validate_source_artifact_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx, kind="source_artifact")

    def validate_derived_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx, kind="derived")

    def validate_explain_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx, kind="explain")

    def public_validate_sql(self, sql: str, ctx: DialectContext) -> dict[str, object]:
        guardrail = guardrail_check(sql, dialect=ctx.sqlglot_dialect)
        return {
            key: value
            for key, value in dict(guardrail).items()
            if not key.startswith("_")
        }

    def build_execution_decision(
        self,
        sql: str,
        ctx: DialectContext,
        *,
        policy: ExecutionPolicy = "readonly",
    ) -> ExecutionSafetyDecision:
        if self.db is None:
            raise ValueError("SqlSafetyService requires a database session to build execution decisions.")

        def schema_validator(generated_sql: str | exp.Expression, db: Session, datasource_id: str) -> list[str]:
            from engine.sql.safety_gate import validate_sql_schema

            return validate_sql_schema(generated_sql, db, datasource_id, dialect=ctx.dialect)

        return TrustGate(self.db, schema_validator).execution_decision(
            ctx.datasource_id,
            sql,
            policy=policy,
        )

    def _validate_readonly_sql(
        self,
        sql: str,
        ctx: DialectContext,
        *,
        kind: SqlValidationKind,
    ) -> list[str]:
        warnings = self._validate_single_select(sql, ctx, kind=kind)
        if warnings:
            return warnings

        guardrail = guardrail_check(sql, dialect=ctx.sqlglot_dialect)
        if guardrail.get("result") == "reject":
            message = str(guardrail.get("message") or "SQL safety guardrail rejected this statement.")
            checks = guardrail.get("checks") or []
            check_messages = [
                str(check.get("message", ""))
                for check in checks
                if isinstance(check, dict) and check.get("message")
            ]
            return [message, *check_messages]
        return []

    @staticmethod
    def _validate_single_select(sql: str, ctx: DialectContext, *, kind: SqlValidationKind) -> list[str]:
        label = {
            "source_artifact": "Source SQL",
            "derived": "Derived SQL",
            "explain": "Explain SQL",
            "agent": "Agent SQL",
            "user": "User SQL",
        }[kind]
        try:
            exprs = sqlglot.parse(sql, read=ctx.sqlglot_dialect)
        except Exception as exc:
            return [f"{label} validation parse error: {exc}"]
        if len(exprs) != 1:
            return [f"{label} must be a single statement."]
        if not isinstance(exprs[0], exp.Select):
            return [f"{label} must be a SELECT statement."]
        return []
