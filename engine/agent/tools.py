from __future__ import annotations

import re
import time
from typing import Any, Callable

import sqlglot
from sqlalchemy.orm import Session, selectinload
from sqlglot import exp

from engine.ai import generate_sql, validate_sql_schema
from engine.agent.prompts import RESULT_EXPLANATION_SECTIONS
from engine.agent.types import AgentRunRequest, QueryPlan, SQLCandidate, ToolObservation
from engine.errors import DataBoxError
from engine.executor import execute_query
from engine.guardrail import GuardrailResult, guardrail_check
from engine.models import DataSource, SchemaTable
from engine.semantic import QueryPlanBuilder, SchemaContextBuilder, SchemaLinker
from engine.trust_gate import TrustGate


ToolBody = Callable[[], dict[str, Any]]


def build_schema_context_tool(db: Session, req: AgentRunRequest) -> ToolObservation:
    tool_input = {
        "datasource_id": req.datasource_id,
        "question": req.question,
        "optimize_rag": req.optimize_rag,
    }

    def body() -> dict[str, Any]:
        linker = SchemaLinker(db)
        if req.optimize_rag:
            linking_result = linker.link(datasource_id=req.datasource_id, question=req.question)
        else:
            linking_result = linker.full_context(datasource_id=req.datasource_id, question=req.question)

        schema_context = SchemaContextBuilder(db).build(linking_result)
        metadata = linking_result.response_metadata(schema_context)
        return {
            "schema_context": schema_context,
            "candidate_tables": _linked_tables_payload(linking_result.tables),
            "candidate_columns": metadata.get("selectedColumns", []),
            "selected_tables": metadata.get("selectedTables", []),
            "schema_linking_reasons": metadata.get("schemaLinkingReasons", []),
            "schema_context_size": metadata.get("schemaContextSize", 0),
            "original_schema_table_count": metadata.get("originalSchemaTableCount", 0),
            "selected_schema_table_count": metadata.get("selectedSchemaTableCount", 0),
            "mode": linking_result.mode,
        }

    return _observe("build_schema_context", tool_input, body)


def build_query_plan_tool(
    db: Session,
    req: AgentRunRequest,
    schema_context: dict[str, Any] | None = None,
) -> ToolObservation:
    schema_context = schema_context or {}
    selected_tables = [str(item) for item in _list_value(schema_context.get("selected_tables"))]
    tool_input = {
        "datasource_id": req.datasource_id,
        "question": req.question,
        "selected_tables": selected_tables,
    }

    def body() -> dict[str, Any]:
        try:
            plan = QueryPlanBuilder(db).build(
                datasource_id=req.datasource_id,
                question=req.question,
                schema_context=str(schema_context.get("schema_context", "")),
                llm_config=_llm_config(req),
                selected_tables=selected_tables,
            )
            return _agent_query_plan_from_semantic(req.question, plan.to_dict(), selected_tables)
        except Exception as exc:
            return _fallback_query_plan(db, req.datasource_id, req.question, selected_tables, exc)

    return _observe("build_query_plan", tool_input, body)


def generate_sql_tool(db: Session, req: AgentRunRequest) -> ToolObservation:
    tool_input = {
        "datasource_id": req.datasource_id,
        "question": req.question,
        "optimize_rag": req.optimize_rag,
        "model_name": req.model_name,
        "has_api_key": bool(req.api_key),
    }

    def body() -> dict[str, Any]:
        result = generate_sql(
            db,
            req.datasource_id,
            req.question,
            llm_config=_llm_config(req),
            optimize_rag=req.optimize_rag,
        )
        raw_sql = str(result.get("sql", "") or "").strip()
        sql, rewrite_notes = _prepare_generated_sql(db, req.datasource_id, raw_sql)
        candidate = SQLCandidate(
            sql=sql,
            raw_sql=raw_sql if sql != raw_sql else None,
            model=str(result.get("model", "")) or None,
            mode=str(result.get("mode", "")) or None,
            latency_ms=int(result.get("latencyMs", 0) or 0),
            schema_validation_warnings=[str(item) for item in _list_value(result.get("schemaValidationWarnings"))],
            rewrite_notes=rewrite_notes,
            metadata={
                "query_plan": result.get("queryPlan"),
                "selected_tables": result.get("selectedTables", []),
                "selected_columns": result.get("selectedColumns", []),
                "schema_context_size": result.get("schemaContextSize"),
            },
        )
        return candidate.model_dump()

    return _observe("generate_sql_candidate", tool_input, body)


def validate_sql_tool(db: Session, datasource_id: str, sql: str) -> ToolObservation:
    tool_input = {"datasource_id": datasource_id, "sql_preview": _preview_sql(sql)}

    def body() -> dict[str, Any]:
        trust_gate = TrustGate(db, validate_sql_schema).evaluate(datasource_id, sql)
        guardrail = trust_gate["guardrail"]
        schema_warnings = list(trust_gate.get("schemaWarnings", []))
        reject_checks = [item for item in guardrail.get("checks", []) if item.get("level") == "reject"]
        select_star_checks = [item for item in guardrail.get("checks", []) if item.get("rule") == "select_star"]
        auto_limit_only = _is_auto_limit_only(guardrail)
        prod_confirmation = _requires_prod_confirmation(trust_gate)
        requires_confirmation = bool(trust_gate.get("requiresConfirmation")) and not auto_limit_only

        passed = (
            guardrail.get("result") != "reject"
            and not reject_checks
            and not schema_warnings
            and not select_star_checks
            and not prod_confirmation
        )
        can_execute = passed and not requires_confirmation
        revise_suggestion = None if can_execute else _revise_suggestion(
            guardrail=guardrail,
            schema_warnings=schema_warnings,
            requires_confirmation=requires_confirmation,
        )

        return {
            "passed": passed,
            "can_execute": can_execute,
            "safe_sql": guardrail.get("safeSql") if can_execute else None,
            "original_sql": sql,
            "schema_warnings": schema_warnings,
            "guardrail": dict(guardrail),
            "trust_gate": dict(trust_gate),
            "requires_confirmation": requires_confirmation,
            "messages": list(trust_gate.get("messages", [])),
            "revise_suggestion": revise_suggestion,
        }

    return _observe("validate_sql", tool_input, body)


def execute_sql_tool(db: Session, req: AgentRunRequest, sql: str) -> ToolObservation:
    start = time.perf_counter()
    tool_input = {"datasource_id": req.datasource_id, "sql_preview": _preview_sql(sql)}
    try:
        result = execute_query(db, req.datasource_id, sql, question=req.question)
        output = {
            "success": bool(result.get("success")),
            "columns": result.get("columns", []),
            "rows": _sample_rows(result.get("rows", [])),
            "rowCount": result.get("rowCount", 0),
            "latencyMs": result.get("latencyMs", 0),
            "historyId": result.get("historyId"),
            "executionId": result.get("executionId"),
            "truncated": result.get("truncated", False),
            "warnings": result.get("warnings", []),
            "timing": {
                "connectMs": result.get("connectMs", 0),
                "guardrailMs": result.get("guardrailMs", 0),
                "executeMs": result.get("executeMs", 0),
                "fetchMs": result.get("fetchMs", 0),
                "serializeMs": result.get("serializeMs", 0),
                "totalMs": result.get("totalMs", result.get("latencyMs", 0)),
            },
        }
        return _success("execute_sql", tool_input, output, start)
    except Exception as exc:
        output = {
            "success": False,
            "error_type": type(exc).__name__,
            "revise_suggestion": _execution_revise_suggestion(sql, exc),
        }
        return _failed("execute_sql", tool_input, str(exc), start, output)


def revise_sql_tool(
    sql: str | None,
    error: str,
    safety: dict[str, Any] | None = None,
) -> ToolObservation:
    tool_input = {"sql_preview": _preview_sql(sql or ""), "error": error[:500]}

    def body() -> dict[str, Any]:
        suggestion = _revise_suggestion_from_context(sql or "", error, safety or {})
        return {
            "revise_suggestion": suggestion,
            "blocked_sql": sql,
            "reason": error,
        }

    return _observe("revise_sql", tool_input, body)


def explain_result_tool(
    req: AgentRunRequest,
    sql: str | None,
    query_plan: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    safety: dict[str, Any] | None,
) -> ToolObservation:
    tool_input = {
        "has_sql": bool(sql),
        "has_execution": bool(execution),
        "execute": req.execute,
    }

    def body() -> dict[str, Any]:
        columns = [str(item) for item in _list_value((execution or {}).get("columns"))]
        rows = _list_value((execution or {}).get("rows"))
        row_count = int((execution or {}).get("rowCount", len(rows)) or 0)
        plan_goal = (query_plan or {}).get("analysis_goal") or req.question
        passed = bool((safety or {}).get("passed"))

        if execution and execution.get("success"):
            facts = f"Data facts: the query returned {row_count} sampled rows across {len(columns)} columns"
            if columns:
                facts += f" ({', '.join(columns[:8])})."
            else:
                facts += "."
            causes = f"Possible causes: the result reflects the plan goal `{plan_goal}` and should be read as descriptive evidence, not causal proof."
            next_steps = "Recommended next steps: inspect filters, compare another time range or dimension, and save a Golden SQL case if this becomes a recurring metric."
        elif passed and not req.execute:
            facts = "Data facts: SQL generation and safety validation completed, but execution was disabled for this run."
            causes = "Possible causes: execute=false is useful for review-only workflows or production approval gates."
            next_steps = "Recommended next steps: review the safe SQL, then rerun with execute=true when ready."
        else:
            facts = "Data facts: no result set is available."
            causes = "Possible causes: the SQL did not pass validation or execution failed before rows were returned."
            next_steps = "Recommended next steps: apply the revise suggestion, sync schema metadata, and retry."

        return {
            "explanation": "\n".join([facts, causes, next_steps]),
            "mode": "deterministic",
            "policy": RESULT_EXPLANATION_SECTIONS,
        }

    return _observe("explain_result", tool_input, body)


def suggest_chart_tool(execution: dict[str, Any] | None) -> ToolObservation:
    tool_input = {"has_execution": bool(execution)}

    def body() -> dict[str, Any]:
        if not execution or not execution.get("success"):
            return {"type": "table", "x": None, "y": None, "reason": "No successful result set is available."}

        columns = [str(item) for item in _list_value(execution.get("columns"))]
        rows = [item for item in _list_value(execution.get("rows")) if isinstance(item, dict)]
        if not columns or not rows:
            return {"type": "table", "x": None, "y": None, "reason": "Empty result sets are best displayed as a table."}

        numeric_cols = [column for column in columns if any(_is_number(row.get(column)) for row in rows)]
        time_cols = [column for column in columns if _looks_temporal(column, [row.get(column) for row in rows])]
        category_cols = [column for column in columns if column not in numeric_cols]

        if time_cols and numeric_cols:
            return {
                "type": "line",
                "x": time_cols[0],
                "y": numeric_cols[0],
                "reason": "A temporal field plus a numeric measure is best shown as a line chart.",
            }

        if category_cols and numeric_cols:
            chart_type = "pie" if _looks_like_share(numeric_cols[0]) and len(rows) <= 8 else "bar"
            return {
                "type": chart_type,
                "x": category_cols[0],
                "y": numeric_cols[0],
                "reason": "A category field plus a numeric measure is best compared by category.",
            }

        return {
            "type": "table",
            "x": columns[0],
            "y": numeric_cols[0] if numeric_cols else None,
            "reason": "No clear category/time plus numeric pairing was found.",
        }

    return _observe("suggest_chart", tool_input, body)


def _observe(name: str, tool_input: dict[str, Any], body: ToolBody) -> ToolObservation:
    start = time.perf_counter()
    try:
        return _success(name, tool_input, body(), start)
    except Exception as exc:
        return _failed(name, tool_input, str(exc), start)


def _success(name: str, tool_input: dict[str, Any], output: dict[str, Any], start: float) -> ToolObservation:
    return ToolObservation(
        name=name,
        status="success",
        input=tool_input,
        output=output,
        error=None,
        latency_ms=_latency_ms(start),
    )


def _failed(
    name: str,
    tool_input: dict[str, Any],
    error: str,
    start: float,
    output: dict[str, Any] | None = None,
) -> ToolObservation:
    return ToolObservation(
        name=name,
        status="failed",
        input=tool_input,
        output=output,
        error=error,
        latency_ms=_latency_ms(start),
    )


def _skipped(name: str, tool_input: dict[str, Any], output: dict[str, Any] | None = None) -> ToolObservation:
    return ToolObservation(name=name, status="skipped", input=tool_input, output=output or {}, latency_ms=0)


def skipped_execute_observation() -> ToolObservation:
    return _skipped("execute_sql", {"execute": False}, {"reason": "Request execute=false; SQL was not executed."})


def _latency_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _llm_config(req: AgentRunRequest) -> dict[str, Any]:
    if not req.api_key:
        return {}
    return {
        "api_key": req.api_key,
        "api_base": req.api_base or "https://api.openai.com/v1",
        "model": req.model_name or "gpt-4o-mini",
    }


def _linked_tables_payload(table_links: list[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for link in table_links:
        table = link.table
        columns = sorted(table.columns, key=lambda column: (column.ordinal_position or 0, str(column.column_name)))
        payload.append(
            {
                "table": str(table.table_name),
                "comment": str(table.table_comment or ""),
                "score": round(float(getattr(link, "score", 0.0) or 0.0), 3),
                "reasons": list(getattr(link, "reasons", []) or []),
                "columns": [
                    {
                        "name": str(column.column_name),
                        "type": str(column.column_type or column.data_type or ""),
                        "comment": str(column.column_comment or ""),
                        "primary_key": bool(column.is_primary_key),
                        "foreign_key": bool(column.is_foreign_key),
                    }
                    for column in columns
                ],
            }
        )
    return payload


def _agent_query_plan_from_semantic(
    question: str,
    raw_plan: dict[str, Any],
    selected_tables: list[str],
) -> dict[str, Any]:
    risk_notes = [str(item) for item in _list_value(raw_plan.get("warnings"))]
    plan = QueryPlan(
        analysis_goal=str(raw_plan.get("intent") or question),
        metrics=[dict(item) for item in _list_value(raw_plan.get("metrics")) if isinstance(item, dict)],
        dimensions=[dict(item) for item in _list_value(raw_plan.get("dimensions")) if isinstance(item, dict)],
        filters=[dict(item) for item in _list_value(raw_plan.get("filters")) if isinstance(item, dict)],
        time_range=_infer_time_range(question),
        candidate_tables=[str(item) for item in _list_value(raw_plan.get("tables"))] or selected_tables,
        assumptions=[
            f"Plan mode: {raw_plan.get('mode', 'offline')}",
            "Only synced local schema metadata is trusted.",
        ],
        risk_notes=risk_notes,
        raw_plan=raw_plan,
    )
    return plan.model_dump()


def _fallback_query_plan(
    db: Session,
    datasource_id: str,
    question: str,
    selected_tables: list[str],
    exc: Exception,
) -> dict[str, Any]:
    tables = selected_tables or _first_schema_tables(db, datasource_id)
    plan = QueryPlan(
        analysis_goal=question,
        metrics=[],
        dimensions=[],
        filters=[],
        time_range=_infer_time_range(question),
        candidate_tables=tables[:3],
        assumptions=["Deterministic fallback query plan was used."],
        risk_notes=[f"QueryPlanBuilder unavailable: {type(exc).__name__}"],
        raw_plan={
            "intent": "answer_question",
            "tables": tables[:3],
            "mode": "deterministic_fallback",
            "warnings": [str(exc)],
        },
    )
    return plan.model_dump()


def _prepare_generated_sql(db: Session, datasource_id: str, sql: str) -> tuple[str, list[str]]:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        return cleaned, []

    notes: list[str] = []
    rewritten, rewrote_star = _rewrite_select_star(db, datasource_id, cleaned)
    if rewrote_star:
        notes.append("select_star_rewritten_to_explicit_columns")

    guardrail = guardrail_check(rewritten, dialect=_datasource_dialect(db, datasource_id))
    safe_sql = str(guardrail.get("safeSql") or "").strip()
    if guardrail.get("result") != "reject" and safe_sql and safe_sql != rewritten:
        rewritten = safe_sql
        notes.append("limit_added_by_guardrail")

    return rewritten, notes


def _rewrite_select_star(db: Session, datasource_id: str, sql: str) -> tuple[str, bool]:
    try:
        dialect = _sqlglot_dialect(_datasource_dialect(db, datasource_id))
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return sql, False

    if not isinstance(parsed, (exp.Select, exp.Union)):
        return sql, False

    schema = _schema_columns(db, datasource_id)
    if not schema:
        return sql, False

    rewrote = False
    for select in list(parsed.find_all(exp.Select)):
        expressions: list[exp.Expression] = []
        for projection in select.expressions:
            star_table = _star_projection_table(projection)
            if star_table is None:
                expressions.append(projection)
                continue

            expanded = _expanded_star_columns(select, schema, star_table)
            if not expanded:
                expressions.append(projection)
                continue

            rewrote = True
            expressions.extend(expanded)
        if rewrote:
            select.set("expressions", expressions)

    if not rewrote:
        return sql, False
    return parsed.sql(dialect=dialect), True


def _star_projection_table(projection: exp.Expression) -> str | None:
    inner = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(inner, exp.Count):
        return None
    if isinstance(inner, exp.Star):
        return ""
    if isinstance(inner, exp.Column) and isinstance(inner.this, exp.Star):
        return inner.text("table") or ""
    return None


def _expanded_star_columns(
    select: exp.Select,
    schema: dict[str, list[str]],
    star_table: str,
) -> list[exp.Expression]:
    table_nodes = list(select.find_all(exp.Table))
    alias_to_table: dict[str, str] = {}
    for table in table_nodes:
        table_name = table.name.lower()
        alias = str(getattr(table, "alias_or_name", "") or table.name)
        alias_to_table[alias.lower()] = table_name
        alias_to_table[table_name] = table_name

    if star_table:
        table_name = alias_to_table.get(star_table.lower())
        if not table_name or table_name not in schema:
            return []
        return [exp.column(column, table=star_table) for column in schema[table_name][:12]]

    expanded: list[exp.Expression] = []
    for table in table_nodes:
        table_name = table.name.lower()
        if table_name not in schema:
            continue
        qualifier = str(getattr(table, "alias_or_name", "") or table.name)
        expanded.extend(exp.column(column, table=qualifier) for column in schema[table_name][:12])
    return expanded


def _schema_columns(db: Session, datasource_id: str) -> dict[str, list[str]]:
    tables = (
        db.query(SchemaTable)
        .options(selectinload(SchemaTable.columns))
        .filter(SchemaTable.data_source_id == datasource_id)
        .all()
    )
    return {
        str(table.table_name).lower(): [
            str(column.column_name)
            for column in sorted(table.columns, key=lambda item: (item.ordinal_position or 0, str(item.column_name)))
        ]
        for table in tables
    }


def _first_schema_tables(db: Session, datasource_id: str) -> list[str]:
    tables = (
        db.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .order_by(SchemaTable.table_name.asc())
        .limit(3)
        .all()
    )
    return [str(table.table_name) for table in tables]


def _datasource_dialect(db: Session, datasource_id: str) -> str:
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    return str(datasource.db_type or "mysql") if datasource else "mysql"


def _sqlglot_dialect(dialect: str) -> str:
    dialect_lower = dialect.lower()
    if "postgres" in dialect_lower:
        return "postgres"
    if "sqlite" in dialect_lower:
        return "sqlite"
    return "mysql"


def _is_auto_limit_only(guardrail: GuardrailResult) -> bool:
    checks = list(guardrail.get("checks", []))
    warn_checks = [item for item in checks if item.get("level") == "warn"]
    return bool(warn_checks) and all(item.get("rule") == "auto_limit" for item in warn_checks)


def _requires_prod_confirmation(trust_gate: dict[str, Any]) -> bool:
    return any("Production datasource" in str(message) for message in _list_value(trust_gate.get("messages")))


def _revise_suggestion(
    guardrail: GuardrailResult,
    schema_warnings: list[str],
    requires_confirmation: bool,
) -> str:
    checks = list(guardrail.get("checks", []))
    rules = {str(item.get("rule", "")) for item in checks}
    if guardrail.get("result") == "reject":
        return "Rewrite the query as a single read-only SELECT or WITH statement and remove all DDL/DML/system-catalog access."
    if "select_star" in rules:
        return "Replace SELECT * with explicit column names from the synced schema, then keep a LIMIT clause."
    if schema_warnings:
        return "Fix table or column names to match synced schema metadata before execution."
    if requires_confirmation:
        return "This query requires manual review; narrow the SQL and rerun in review-only mode if needed."
    return "Add explicit columns, filters, and LIMIT, then rerun validation."


def _execution_revise_suggestion(sql: str, exc: Exception) -> str:
    message = str(exc).lower()
    if "no such table" in message or "unknown table" in message:
        return "Sync schema metadata and correct the referenced table name."
    if "no such column" in message or "unknown column" in message:
        return "Correct the referenced column names or aliases in the SELECT, JOIN, WHERE, GROUP BY, or ORDER BY clauses."
    if "syntax" in message:
        return "Check SQL syntax and regenerate with explicit fields and a simple LIMIT."
    return "Review the safe SQL, reduce joins or filters, and retry after schema validation."


def _revise_suggestion_from_context(sql: str, error: str, safety: dict[str, Any]) -> str:
    if safety.get("revise_suggestion"):
        return str(safety["revise_suggestion"])
    lowered = error.lower()
    if any(keyword in lowered for keyword in ("drop", "delete", "update", "insert", "alter", "truncate", "merge")):
        return "Remove write operations. The agent can only produce SELECT or WITH queries."
    if "*" in sql:
        return "Replace SELECT * with explicit columns and add a LIMIT."
    return "Regenerate the SQL using only existing schema tables and columns, explicit projections, and a safe LIMIT."


def _infer_time_range(question: str) -> dict[str, Any] | None:
    q = question.lower()
    match = re.search(r"(?:last|past)\s+(\d+)\s+(day|days|month|months|year|years)", q)
    if match:
        return {"description": match.group(0), "value": int(match.group(1)), "unit": match.group(2)}

    chinese_match = re.search(r"(最近|过去|近)\s*(\d+)\s*(天|日|个月|月|年)", question)
    if chinese_match:
        return {
            "description": chinese_match.group(0),
            "value": int(chinese_match.group(2)),
            "unit": chinese_match.group(3),
        }
    if any(token in q for token in ("today", "yesterday", "daily")):
        return {"description": "relative_time_mentioned"}
    return None


def _sample_rows(rows: Any, limit: int = 100) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [dict(item) for item in rows[:limit] if isinstance(item, dict)]


def _preview_sql(sql: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", sql or "").strip()
    return compact[:limit] + ("..." if len(compact) > limit else "")


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False
    return False


def _looks_temporal(column: str, values: list[Any]) -> bool:
    name = column.lower()
    if any(token in name for token in ("date", "time", "day", "month", "year", "created_at", "updated_at")):
        return True
    return any(isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value) for value in values)


def _looks_like_share(column: str) -> bool:
    name = column.lower()
    return any(token in name for token in ("share", "ratio", "rate", "percent", "pct"))
