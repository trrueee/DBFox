from __future__ import annotations

import logging
import os
import sys
from typing import Any

import sqlglot
from sqlglot import exp
from sqlalchemy.orm import Session

from engine.errors import GuardrailValidationError
from engine.models import DataSource, SchemaTable
from engine.sql.trust_gate import ExecutionPolicy, ExecutionSafetyDecision, TrustGate

logger = logging.getLogger("dbfox.sql.executor")


def guardrail_bypass_allowed() -> bool:
    """Centralized check for guardrail bypass availability.

    Requires both DBFOX_TESTING=1 and DBFOX_ALLOW_GUARDRAIL_BYPASS=1.
    Always denied in frozen (packaged) builds.
    """
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        if os.environ.get("DBFOX_TESTING") == "1" or os.environ.get("DBFOX_ALLOW_GUARDRAIL_BYPASS") == "1":
            logger.critical(
                "Guardrail bypass env vars detected in frozen build — ignoring."
            )
        return False
    if os.environ.get("DBFOX_TESTING") != "1":
        return False
    if os.environ.get("DBFOX_ALLOW_GUARDRAIL_BYPASS") != "1":
        return False
    return True


def _resolve_execution_safety_decision(
    db: Session,
    datasource_id: str,
    sql_str: str,
    bypass_guardrail: bool,
    safety_decision: ExecutionSafetyDecision | dict[str, Any] | None,
    policy: ExecutionPolicy = "readonly",
) -> ExecutionSafetyDecision:
    if safety_decision is not None:
        decision = (
            safety_decision
            if isinstance(safety_decision, ExecutionSafetyDecision)
            else ExecutionSafetyDecision.model_validate(safety_decision)
        )
        if decision.datasource_id != datasource_id:
            raise GuardrailValidationError(
                "TrustGate decision datasource does not match the execution datasource.",
                checks=[{
                    "rule": "safety_decision_datasource_mismatch",
                    "level": "reject",
                    "message": "The supplied safety decision belongs to a different datasource.",
                }],
            )
        supplied_sql = sql_str.strip()
        decision_sqls = {
            decision.original_sql.strip(),
            str(decision.safe_sql or "").strip(),
        }
        if supplied_sql not in decision_sqls:
            raise GuardrailValidationError(
                "TrustGate decision SQL does not match the SQL requested for execution.",
                checks=[{
                    "rule": "safety_decision_sql_mismatch",
                    "level": "reject",
                    "message": "The supplied safety decision was created for different SQL text.",
                }],
            )
        return decision

    if bypass_guardrail:
        if not guardrail_bypass_allowed():
            raise GuardrailValidationError(
                "TrustGate bypass is only available in the test environment.",
                checks=[{
                    "rule": "trust_gate_bypass_disabled",
                    "level": "reject",
                    "message": "bypass_guardrail requires DBFOX_TESTING=1 and DBFOX_ALLOW_GUARDRAIL_BYPASS=1.",
                }],
            )
        # Double-gate: bypass is only allowed on dev/test datasources.
        # Prevents DBFOX_TESTING=1 from being inadvertently set in staging/prod.
        ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
        ds_env = (ds.env or "").lower() if ds else ""
        if ds_env not in ("", "dev", "test", "unknown"):
            raise GuardrailValidationError(
                "TrustGate bypass is not allowed on non-dev datasources.",
                checks=[{
                    "rule": "trust_gate_bypass_env_blocked",
                    "level": "reject",
                    "message": f"bypass_guardrail blocked: datasource env is '{ds_env}', only dev/test allowed.",
                }],
            )
        logger.warning(
            "TrustGate bypass active: datasource=%s env=%s policy=%s",
            datasource_id, ds_env, policy,
        )
        guard_res = {
            "result": "pass",
            "originalSql": sql_str,
            "safeSql": sql_str,
            "checks": [],
            "message": "Bypassed via system request (DBFOX_TESTING=1 + DBFOX_ALLOW_GUARDRAIL_BYPASS=1 + dev/test env)",
        }
        return ExecutionSafetyDecision(
            datasource_id=datasource_id,
            policy=policy,
            original_sql=sql_str,
            safe_sql=sql_str,
            passed=True,
            can_execute=True,
            requires_confirmation=False,
            guardrail=guard_res,  # type: ignore[arg-type]
            schema_warnings=[],
            scope_state={
                "datasource_id": datasource_id,
                "bypass_guardrail": True,
                "testing": os.environ.get("DBFOX_TESTING") == "1",
            },
            messages=["Guardrail bypass was used; prefer explicit non-query execution helpers."],
        )

    return TrustGate(db, validate_sql_schema).execution_decision(datasource_id, sql_str, policy=policy)


def _decision_checks_for_history(decision: ExecutionSafetyDecision) -> list[dict[str, Any]]:
    checks = [dict(item) for item in decision.guardrail.get("checks", [])]
    checks.extend(
        {
            "rule": "schema_validation",
            "level": "reject",
            "message": warning,
        }
        for warning in decision.schema_warnings
    )
    if decision.requires_confirmation:
        checks.append(
            {
                "rule": "requires_confirmation",
                "level": "reject",
                "message": "Execution requires manual confirmation before a result set can be produced.",
            }
        )
    for reason in decision.blocked_reasons:
        if reason in {"guardrail_reject", "schema_validation", "requires_confirmation"}:
            continue
        checks.append(
            {
                "rule": reason,
                "level": "reject",
                "message": f"TrustGate blocked execution because of {reason}.",
            }
        )
    if not decision.scope_state.get("datasource_exists", True):
        checks.append(
            {
                "rule": "datasource_scope",
                "level": "reject",
                "message": "Datasource scope could not be resolved for this execution.",
            }
        )
    return checks


def _decision_checks_for_error(decision: ExecutionSafetyDecision) -> list[dict[str, str]]:
    return [
        {
            "rule": str(item.get("rule", "trust_gate")),
            "level": str(item.get("level", "reject")),
            "message": str(item.get("message", "")),
        }
        for item in _decision_checks_for_history(decision)
    ]


def _decision_block_message(decision: ExecutionSafetyDecision) -> str:
    if decision.guardrail.get("result") == "reject":
        return str(decision.guardrail.get("message") or "TrustGate blocked execution.")
    if "select_star" in decision.blocked_reasons:
        return "Agent execution requires explicit projected columns instead of SELECT *."
    if "schema_validation" in decision.blocked_reasons or decision.schema_warnings:
        return "TrustGate blocked execution because schema validation found unknown tables or columns."
    if "requires_confirmation" in decision.blocked_reasons or decision.requires_confirmation:
        return "TrustGate blocked execution because this datasource requires manual confirmation."
    if "safe_sql_missing" in decision.blocked_reasons:
        return "Guardrail did not produce safe_sql. Execution is blocked."
    if "datasource_scope" in decision.blocked_reasons:
        return "Datasource scope could not be resolved."

    explain_detail = next(
        (
            msg
            for msg in decision.messages
            if msg.startswith("EXPLAIN dry-run failed") or msg.startswith("EXPLAIN dry-run unavailable")
        ),
        "",
    )
    suffix = f"（{explain_detail}）" if explain_detail else ""
    if "schema_error" in decision.blocked_reasons:
        return f"表或字段在目标数据库中不存在，本地 Schema 元数据可能已过期，请重新同步 Schema 后重试。{suffix}"
    if "syntax_error" in decision.blocked_reasons:
        return f"SQL 语法未通过目标数据库校验，请检查语句。{suffix}"
    if "explain_unavailable" in decision.blocked_reasons:
        return f"无法连接到目标数据库，数据源可能已离线，请在数据源管理中检查连接后重试。{suffix}"
    if explain_detail:
        return explain_detail

    return "TrustGate blocked execution before SQL reached the database."


def validate_sql_schema(generated_sql: str | exp.Expression, db: Session, datasource_id: str) -> list[str]:
    """Check generated SQL for hallucinated tables/columns against local schema cache."""
    warnings = []
    try:
        tables = db.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).all()
        if not tables:
            return []

        valid_schema = {t.table_name.lower(): {c.column_name.lower() for c in t.columns} for t in tables}
        if isinstance(generated_sql, exp.Expression):
            parsed = generated_sql
        else:
            parsed = sqlglot.parse_one(str(generated_sql), read="mysql")

        projection_aliases = {
            alias.alias.lower()
            for alias in parsed.find_all(exp.Alias)
            if alias.alias
        }

        # Collect CTE names and subquery aliases to avoid false positive warnings
        ctes = {cte.alias.lower() for cte in parsed.find_all(exp.CTE) if cte.alias}
        subquery_aliases = {sub.alias.lower() for sub in parsed.find_all(exp.Subquery) if sub.alias}
        temp_sources = ctes | subquery_aliases

        query_tables = []
        for table_node in parsed.find_all(exp.Table):
            t_name = table_node.name.lower()
            if t_name in temp_sources:
                continue
            query_tables.append(t_name)
            if t_name not in valid_schema:
                warnings.append(f"生成 SQL 包含不存在的表: `{table_node.name}`")

        for col_node in parsed.find_all(exp.Column):
            col_name = col_node.name.lower()
            if col_name == "*" or not col_name:
                continue
            col_table_ref = col_node.text("table").lower()
            if (
                not col_table_ref
                and col_name in projection_aliases
                and _is_projection_alias_reference(col_node)
            ):
                continue
            target_table = None
            if col_table_ref:
                for t_node in parsed.find_all(exp.Table):
                    alias = t_node.alias.lower() if t_node.alias else ""
                    if alias == col_table_ref or t_node.name.lower() == col_table_ref:
                        target_table = t_node.name.lower()
                        break
            if target_table:
                if target_table in temp_sources:
                    continue
                if target_table in valid_schema:
                    if col_name not in valid_schema[target_table]:
                        warnings.append(f"生成 SQL 包含表 `{target_table}` 中不存在的字段: `{col_node.name}`")
            else:
                if temp_sources:
                    continue
                queried_valid_tables = [t for t in query_tables if t in valid_schema]
                if queried_valid_tables:
                    exists_in_any = any(col_name in valid_schema[t] for t in queried_valid_tables)
                    if not exists_in_any:
                        tbl_list = ", ".join(f"`{t}`" for t in queried_valid_tables)
                        warnings.append(f"生成 SQL 中的字段 `{col_node.name}` 不存在于查询的表 {tbl_list} 中")
    except Exception as e:
        logger.warning("Schema validation error: %s", e)
    return warnings


def _is_projection_alias_reference(col_node: exp.Column) -> bool:
    parent = col_node.parent
    while parent is not None:
        if isinstance(parent, (exp.Order, exp.Ordered, exp.Group, exp.Having, exp.Qualify)):
            return True
        if isinstance(parent, exp.Select):
            return False
        parent = parent.parent
    return False
