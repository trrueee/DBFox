from __future__ import annotations

from sqlalchemy.orm import Session
from collections.abc import Mapping
from typing import Any
from sqlglot import exp

from dlcs.dbfox_data.backend.sql.dialect_context import DatabaseDialectContext
from dlcs.dbfox_data.backend.sql.guardrail import guardrail_check, guardrail_check_with_ast
from dlcs.dbfox_data.backend.sql.safety_contracts import (
    DatabaseSafetyScope,
    ExecutionPolicy,
    ExecutionSafetyDecision,
)
from dlcs.dbfox_data.backend.sql.trust_gate import TrustGate


class SqlSafetyService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def validate_user_sql(self, sql: str, ctx: DatabaseDialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_agent_sql(self, sql: str, ctx: DatabaseDialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_source_artifact_sql(self, sql: str, ctx: DatabaseDialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_derived_sql(self, sql: str, ctx: DatabaseDialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def validate_explain_sql(self, sql: str, ctx: DatabaseDialectContext) -> list[str]:
        return self._validate_readonly_sql(sql, ctx)

    def public_validate_sql(self, sql: str, ctx: DatabaseDialectContext) -> dict[str, object]:
        guardrail = guardrail_check(sql, dialect=ctx.sqlglot_dialect)
        return {
            key: value
            for key, value in dict(guardrail).items()
            if not key.startswith("_")
        }

    def build_execution_decision(
        self,
        sql: str,
        ctx: DatabaseDialectContext,
        *,
        policy: ExecutionPolicy = "readonly",
        parameters: Mapping[str, Any] | None = None,
    ) -> ExecutionSafetyDecision:
        if self.db is None:
            raise ValueError("SqlSafetyService requires a database session to build execution decisions.")

        from engine.models import DataSource
        from engine.sql.dry_run import dry_run_query

        datasource = self.db.query(DataSource).filter(DataSource.id == ctx.resource_id).first()
        scope = DatabaseSafetyScope(
            resource_id=ctx.resource_id,
            exists=datasource is not None,
            dialect=str(datasource.db_type or ctx.dialect) if datasource else ctx.dialect,
            environment=str(datasource.env or "dev").lower() if datasource else "unknown",
            is_read_only=bool(datasource.is_read_only) if datasource else None,
            project_id=(
                str(datasource.project_id)
                if datasource is not None and datasource.project_id
                else None
            ),
        )

        def schema_validator(generated_sql: str | exp.Expression) -> list[str]:
            from engine.sql.safety_gate import validate_sql_schema

            return validate_sql_schema(
                generated_sql,
                self.db,
                ctx.resource_id,
                dialect=ctx.dialect,
            )

        def dry_run_validator(
            safe_sql: str,
            bound_parameters: Mapping[str, Any] | None,
        ):
            return dry_run_query(
                self.db,
                ctx.resource_id,
                safe_sql,
                parameters=bound_parameters,
            )

        return TrustGate(schema_validator, dry_run_validator).execution_decision(
            scope,
            sql,
            policy=policy,
            parameters=parameters,
        )

    def _validate_readonly_sql(
        self,
        sql: str,
        ctx: DatabaseDialectContext,
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
