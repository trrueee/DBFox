from __future__ import annotations

from sqlalchemy.orm import Session
from sqlglot import exp

from engine.sql.dialect_context import DialectContext
from engine.sql.guardrail import guardrail_check, guardrail_check_with_ast
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate


class SqlSafetyService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def validate_user_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_agent_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_source_artifact_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_derived_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_explain_sql(self, sql: str, ctx: DialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

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
    ) -> list[str]:
        guardrail, _expression = guardrail_check_with_ast(
            sql,
            dialect=ctx.sqlglot_dialect,
        )
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
