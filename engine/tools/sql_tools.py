from __future__ import annotations

import re
import time
import json
from typing import Any, Callable

import sqlglot
from sqlalchemy.orm import Session, selectinload
from sqlglot import exp

from engine.sql.generator import generate_sql_from_schema_context, validate_sql_schema
from engine.agent_core.answer import synthesize_agent_answer
from engine.agent_core.context import analysis_question, context_summary, referenced_artifact_ids, schema_linking_question
from engine.agent_core.prompts import RESULT_EXPLANATION_SECTIONS
from engine.agent_core.recommendations import suggest_followups
from engine.agent_core.result_profiler import profile_result
from engine.agent_core.semantic_contract import QueryContract, build_query_contract
from engine.agent_core.semantic_retry_policy import (
    accept_semantic_retry,
    semantic_retry_prompt,
    semantic_violation_payload,
    should_retry_semantic,
)
from engine.agent_core.sql_semantic_verifier import verify_sql_against_contract
from engine.agent_core.types import AgentRunRequest, QueryPlan, ReviseResult, SQLCandidate, ToolObservation
from engine.errors import DataBoxError
from engine.sql.executor import execute_query
from engine.sql.guardrail import GuardrailResult, guardrail_check
from engine.models import DataSource, SchemaTable
from engine.semantic import QueryPlanBuilder, SchemaContextBuilder, SchemaLinker
from engine.sql.trust_gate import TrustGate


ToolBody = Callable[[], dict[str, Any]]
STAR_EXPANSION_LIMIT = 12


def load_followup_context_tool(req: AgentRunRequest) -> ToolObservation:
    context = req.follow_up_context
    tool_input = {
        "session_id": req.session_id or (context.session_id if context else None),
        "parent_run_id": req.parent_run_id or (context.parent_run_id if context else None),
        "artifact_count": len(context.artifacts) if context else 0,
    }

    def body() -> dict[str, Any]:
        return {
            "context_summary": context_summary(req),
            "analysis_question": analysis_question(req),
            "schema_linking_question": schema_linking_question(req),
            "referenced_artifact_ids": referenced_artifact_ids(req),
        }

    return _observe("load_follow_up_context", tool_input, body)


def build_schema_context_tool(db: Session, req: AgentRunRequest) -> ToolObservation:
    question = schema_linking_question(req)
    tool_input = {
        "datasource_id": req.datasource_id,
        "question": req.question,
        "has_follow_up_context": bool(req.follow_up_context),
        "optimize_rag": req.optimize_rag,
    }

    def body() -> dict[str, Any]:
        linker = SchemaLinker(db)
        if req.optimize_rag:
            linking_result = linker.link(datasource_id=req.datasource_id, question=question)
        else:
            linking_result = linker.full_context(datasource_id=req.datasource_id, question=question)

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
    question = analysis_question(req)
    selected_tables = [str(item) for item in _list_value(schema_context.get("selected_tables"))]
    tool_input = {
        "datasource_id": req.datasource_id,
        "question": req.question,
        "has_follow_up_context": bool(req.follow_up_context),
        "selected_tables": selected_tables,
    }

    def body() -> dict[str, Any]:
        try:
            plan = QueryPlanBuilder(db).build(
                datasource_id=req.datasource_id,
                question=question,
                schema_context=str(schema_context.get("schema_context", "")),
                llm_config=_llm_config(req),
                selected_tables=selected_tables,
            )
            return _agent_query_plan_from_semantic(req.question, plan.to_dict(), selected_tables)
        except Exception as exc:
            return _fallback_query_plan(db, req.datasource_id, question, selected_tables, exc)

    return _observe("build_query_plan", tool_input, body)


def generate_sql_tool(
    db: Session,
    req: AgentRunRequest,
    schema_context: dict[str, Any] | None = None,
    query_plan: dict[str, Any] | None = None,
) -> ToolObservation:
    schema_context = schema_context or {}
    query_plan = query_plan or {}
    question = analysis_question(req)
    tool_input = {
        "datasource_id": req.datasource_id,
        "question": req.question,
        "has_follow_up_context": bool(req.follow_up_context),
        "optimize_rag": req.optimize_rag,
        "model_name": req.model_name,
        "has_api_key": bool(req.api_key),
        "plan_goal": query_plan.get("analysis_goal"),
        "plan_candidate_tables": query_plan.get("candidate_tables", []),
        "schema_context_size": schema_context.get("schema_context_size", 0),
    }

    def body() -> dict[str, Any]:
        semantic_mode = getattr(req, "semantic_mode", "off") or "off"
        dialect = _datasource_dialect(db, req.datasource_id)
        schema_text = str(schema_context.get("schema_context") or "")
        result = generate_sql_from_schema_context(
            question=req.question,
            schema_context=schema_text,
            dialect=dialect,
            llm_config=_llm_config(req),
        )
        raw_sql = str(result.get("sql", "") or "").strip()
        sql = raw_sql or None

        semantic_retry_attempted = False
        semantic_retry_accepted = False
        semantic_retry_rejected_reason: str | None = None
        semantic_initial_violations: list[dict[str, Any]] = []
        semantic_violations: list[Any] = []
        semantic_retry_violations: list[Any] = []
        semantic_contract = (
            build_query_contract(question, schema_context, None) if semantic_mode != "off" else None
        )

        if sql and semantic_mode != "off" and semantic_contract is not None:
            semantic_violations = verify_sql_against_contract(sql, semantic_contract, schema_context)
            semantic_initial_violations = semantic_violation_payload(semantic_violations)

            if semantic_mode == "retry" and should_retry_semantic(semantic_contract, semantic_violations, req.api_key):
                semantic_retry_attempted = True
                retry_prompt = semantic_retry_prompt(
                    question=question,
                    schema_context=schema_context,
                    contract=semantic_contract,
                    previous_sql=sql,
                    violations=semantic_violations,
                )
                retry_result = generate_sql_from_schema_context(
                    question=retry_prompt,
                    schema_context=schema_text,
                    dialect=dialect,
                    llm_config=_llm_config(req),
                )
                retry_sql_candidate = str(retry_result.get("sql", "") or "").strip()
                if retry_sql_candidate:
                    retry_violations = verify_sql_against_contract(
                        retry_sql_candidate, semantic_contract, schema_context
                    )
                    semantic_retry_violations = semantic_violation_payload(retry_violations)
                    if accept_semantic_retry(
                        semantic_violations,
                        retry_violations,
                        semantic_contract,
                        original_sql=sql,
                        retry_sql=retry_sql_candidate,
                    ):
                        semantic_retry_accepted = True
                        result = retry_result
                        raw_sql = retry_sql_candidate
                        sql = retry_sql_candidate
                        semantic_violations = retry_violations
                    else:
                        semantic_retry_rejected_reason = "retry_did_not_improve_violations"
                else:
                    semantic_retry_rejected_reason = "retry_produced_empty_sql"

        result_metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        candidate = SQLCandidate(
            sql=sql,
            raw_sql=raw_sql if sql != raw_sql else None,
            model=str(result.get("model", "")) or None,
            mode=str(result.get("mode", "")) or None,
            latency_ms=int(result.get("latencyMs", 0) or 0),
            schema_validation_warnings=[str(item) for item in _list_value(result.get("schemaValidationWarnings"))],
            rewrite_notes=[],
            error=str(result.get("error")) if result.get("error") else None,
            metadata={
                **result_metadata,
                "generation_source": "schema_direct_llm",
                "used_renderer": False,
                "used_query_plan": False,
                "used_query_plan_as_prompt": False,
                "used_guardrail_in_generate": False,
                "used_semantic_retry": semantic_retry_accepted,
                "agent_query_plan": query_plan,
                "query_plan": result.get("queryPlan"),
                "selected_tables": result.get("selectedTables", []),
                "selected_columns": result.get("selectedColumns", []),
                "schema_context_size": result.get("schemaContextSize"),
                "error": result.get("error"),
                "semantic_mode": semantic_mode,
                "semantic_contract": semantic_contract.to_dict() if semantic_contract is not None else None,
                "semantic_violations": semantic_violation_payload(semantic_violations),
                "semantic_initial_violations": semantic_initial_violations,
                "semantic_retry_attempted": semantic_retry_attempted,
                "semantic_retry_accepted": semantic_retry_accepted,
                "semantic_retry_rejected_reason": semantic_retry_rejected_reason,
                "semantic_retry_violations": semantic_retry_violations,
            },
        )
        return candidate.model_dump()

    return _observe("generate_sql_candidate", tool_input, body)


def validate_sql_tool(db: Session, datasource_id: str, sql: str) -> ToolObservation:
    tool_input = {"datasource_id": datasource_id, "sql_preview": _preview_sql(sql)}

    def body() -> dict[str, Any]:
        prepared_sql, rewrite_notes, rewrite_metadata = _prepare_generated_sql(db, datasource_id, sql)
        candidate_sql = prepared_sql or sql
        gate = TrustGate(db, validate_sql_schema)
        trust_gate = gate.evaluate(datasource_id, candidate_sql)
        execution_decision = gate.execution_decision(datasource_id, candidate_sql, policy="agent_readonly")
        guardrail = execution_decision.guardrail
        schema_warnings = list(execution_decision.schema_warnings)
        revise_suggestion = None if execution_decision.can_execute else _revise_suggestion(
            guardrail=guardrail,
            schema_warnings=schema_warnings,
            requires_confirmation=execution_decision.requires_confirmation,
        )

        return {
            "passed": execution_decision.passed,
            "can_execute": execution_decision.can_execute,
            "safe_sql": execution_decision.safe_sql,
            "original_sql": sql,
            "prepared_sql": prepared_sql,
            "rewrite_notes": rewrite_notes,
            "rewrite": rewrite_metadata,
            "schema_warnings": schema_warnings,
            "guardrail": dict(guardrail),
            "trust_gate": dict(trust_gate),
            "execution_safety_decision": execution_decision.model_dump(mode="json"),
            "requires_confirmation": execution_decision.requires_confirmation,
            "messages": list(execution_decision.messages),
            "blocked_reasons": list(execution_decision.blocked_reasons),
            "revise_suggestion": revise_suggestion,
        }

    return _observe("validate_sql", tool_input, body)


def execute_sql_tool(
    db: Session,
    req: AgentRunRequest,
    sql: str,
    safety: dict[str, Any] | None = None,
) -> ToolObservation:
    start = time.perf_counter()
    tool_input = {"datasource_id": req.datasource_id, "sql_preview": _preview_sql(sql)}
    try:
        result = execute_query(
            db,
            req.datasource_id,
            sql,
            question=req.question,
            safety_decision=(safety or {}).get("execution_safety_decision"),
        )
        output = {
            "success": bool(result.get("success")),
            "columns": result.get("columns", []),
            "rows": _sample_rows(result.get("rows", [])),
            "rowCount": result.get("rowCount", 0),
            "latencyMs": result.get("latencyMs", 0),
            "historyId": result.get("historyId"),
            "executionId": result.get("executionId"),
            "safetyDecision": result.get("safetyDecision"),
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
    db: Session | None = None,
    datasource_id: str | None = None,
) -> ToolObservation:
    tool_input = {"sql_preview": _preview_sql(sql or ""), "error": error[:500]}

    def body() -> dict[str, Any]:
        suggestion = _revise_suggestion_from_context(sql or "", error, safety or {})
        fix = _try_fix_sql(db, datasource_id, sql or "", safety or {})
        result = ReviseResult(
            can_fix=fix["can_fix"],
            fixed_sql=fix["fixed_sql"],
            reason=error,
            changes=fix["changes"],
            remaining_risks=fix["remaining_risks"],
            revise_suggestion=suggestion,
            blocked_sql=sql,
        )
        return result.model_dump()

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
        plan_goal = (query_plan or {}).get("analysis_goal") or req.question
        passed = bool((safety or {}).get("passed"))

        if execution and execution.get("success"):
            columns = [str(item) for item in _list_value((execution or {}).get("columns"))]
            rows = _list_value((execution or {}).get("rows"))
            row_count = int((execution or {}).get("rowCount", len(rows)) or 0)
            facts = f"Data facts: the query returned {row_count} sampled rows across {len(columns)} columns"
            if columns:
                facts += f" ({', '.join(columns[:8])})."
            else:
                facts += "."
            causes = f"Possible causes: the result reflects the plan goal `{plan_goal}` and should be read as descriptive evidence, not causal proof."
            next_steps = "Recommended next steps: inspect filters, compare another time range or dimension, and save a Golden SQL case if this becomes a recurring metric."
        elif passed and not req.execute:
            facts = "Data facts: SQL generation and safety validation completed, but execution was disabled for this run."
            causes = "Possible causes: execute=false skips execution; no data was retrieved from the database."
            next_steps = "Recommended next steps: review the safe SQL, then rerun with execute=true when ready. Do not draw data conclusions without execution results."
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


def profile_result_tool(
    req: AgentRunRequest,
    query_plan: dict[str, Any] | None,
    execution: dict[str, Any] | None,
) -> ToolObservation:
    tool_input = {
        "question": req.question,
        "has_execution": bool(execution),
        "execution_success": bool((execution or {}).get("success")),
    }

    def body() -> dict[str, Any]:
        columns = [str(item) for item in _list_value((execution or {}).get("columns"))]
        rows = [dict(item) for item in _list_value((execution or {}).get("rows")) if isinstance(item, dict)]
        profile = profile_result(
            question=req.question,
            columns=columns,
            rows=rows,
            query_plan=query_plan,
            execution_success=bool((execution or {}).get("success")),
        )
        return profile.model_dump()

    return _observe("profile_result", tool_input, body)


def answer_synthesizer_tool(
    req: AgentRunRequest,
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: dict[str, Any] | None,
    suggestions: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> ToolObservation:
    tool_input = {
        "question": req.question,
        "has_sql": bool(sql),
        "has_profile": bool(result_profile),
        "has_error": bool(error),
    }

    def body() -> dict[str, Any]:
        from engine.agent_core.types import FollowUpSuggestion, ResultProfile

        profile = ResultProfile.model_validate(result_profile) if result_profile else None
        parsed_suggestions = [
            FollowUpSuggestion.model_validate(item)
            for item in (suggestions or [])
            if isinstance(item, dict)
        ]
        answer = synthesize_agent_answer(
            question=req.question,
            query_plan=query_plan,
            sql=sql,
            safety=safety,
            execution=execution,
            result_profile=profile,
            suggestions=parsed_suggestions,
            error=error,
        )
        return answer.model_dump()

    return _observe("answer_synthesizer", tool_input, body)


def suggest_followups_tool(
    req: AgentRunRequest,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: dict[str, Any] | None,
    chart_suggestion: dict[str, Any] | None,
) -> ToolObservation:
    tool_input = {
        "question": req.question,
        "has_profile": bool(result_profile),
        "has_chart": bool(chart_suggestion),
    }

    def body() -> dict[str, Any]:
        from engine.agent_core.types import ResultProfile

        profile = ResultProfile.model_validate(result_profile) if result_profile else None
        suggestions = suggest_followups(
            question=req.question,
            result_profile=profile,
            chart_suggestion=chart_suggestion,
            sql=sql,
            safety=safety,
            execution=execution,
        )
        return {"suggestions": [suggestion.model_dump() for suggestion in suggestions]}

    return _observe("suggest_followups", tool_input, body)


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


def _render_sql_from_query_plan(
    db: Session,
    datasource_id: str,
    query_plan: dict[str, Any] | None,
) -> str | None:
    """EXPERIMENTAL: not used in default Text-to-SQL path."""
    if not query_plan:
        return None

    raw_plan: dict[str, Any] = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan  # type: ignore[assignment]
    schema = _schema_columns(db, datasource_id)
    if not schema:
        return None

    tables = [
        str(table)
        for table in _list_value(raw_plan.get("tables"))
        if str(table).lower() in schema
    ]
    if not tables:
        tables = [
            str(table)
            for table in _list_value(query_plan.get("candidate_tables"))
            if str(table).lower() in schema
        ]
    if not tables:
        return None

    base_table = tables[0]
    metrics = [item for item in _list_value(raw_plan.get("metrics")) if isinstance(item, dict)]
    dimensions = [item for item in _list_value(raw_plan.get("dimensions")) if isinstance(item, dict)]
    filters = [item for item in _list_value(raw_plan.get("filters")) if isinstance(item, dict)]
    joins = [item for item in _list_value(raw_plan.get("joins")) if isinstance(item, dict)]
    intent = str(raw_plan.get("intent") or query_plan.get("analysis_goal") or "").strip()
    # If plan indicates very simple answer intent with no metrics/dimensions/filters, nothing to render
    if intent == "answer_question" and not metrics and not dimensions and not filters:
        return None

    # Guard: complex intents require LLM-generated SQL. If so, bail out here.
    requires, reason = _plan_requires_llm_sql(query_plan, question=(query_plan or {}).get("analysis_goal"))
    if requires:
        return None

    projections: list[str] = []
    group_by: list[str] = []
    for dimension in dimensions:
        column = str(dimension.get("column") or "").strip()
        if not column:
            continue
        expression = _dimension_expression(column, dimension.get("transform"))
        alias = _safe_alias(str(dimension.get("name") or "dimension"))
        projections.append(f"{expression} AS {alias}")
        group_by.append(expression)

    for metric in metrics:
        expression = str(metric.get("expression") or "").strip()
        if not expression:
            continue
        alias = _safe_alias(str(metric.get("name") or "metric"))
        projections.append(f"{expression} AS {alias}")

    if not projections:
        projections = [f"{base_table}.{column}" for column in schema[base_table.lower()][:STAR_EXPANSION_LIMIT]]

    sql_parts = [f"SELECT {', '.join(projections)}", f"FROM {base_table}"]
    joined_tables = {base_table.lower()}
    for join in joins:
        right_table = str(join.get("right_table") or "").strip()
        condition = str(join.get("condition") or "").strip()
        if not right_table or right_table.lower() not in schema or right_table.lower() in joined_tables or not condition:
            continue
        condition_refs = _condition_table_refs(condition)
        if condition_refs and not condition_refs.issubset(joined_tables | {right_table.lower()}):
            continue
        sql_parts.append(f"JOIN {right_table} ON {condition}")
        joined_tables.add(right_table.lower())

    where_clauses = [_filter_expression(item) for item in filters]
    # If any filter expression signals 'unsupported', bail out to let LLM generation run
    if any(item == "unsupported" for item in where_clauses):
        return None
    where_clauses = [item for item in where_clauses if item]
    if where_clauses:
        sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")

    if metrics and group_by:
        sql_parts.append(f"GROUP BY {', '.join(group_by)}")

    order_by_raw = raw_plan.get("order_by")
    order_by = _render_order_by(order_by_raw, schema, tables)
    if order_by_raw:
        import logging
        logging.getLogger("databox.agent.tools").info(
            "render_sql: order_by raw=%r -> coerced=%r", order_by_raw, order_by
        )
    if order_by:
        sql_parts.append(f"ORDER BY {order_by}")

    limit_value = raw_plan.get("limit") or query_plan.get("limit")
    # Aggregate-only (metrics, no dimensions): no LIMIT.
    # LIMIT on COUNT(*)/AVG() is harmless but clutter.
    if limit_value is not None and not (metrics and not dimensions):
        limit = _coerce_limit(limit_value)
        sql_parts.append(f"LIMIT {limit}")
    return " ".join(sql_parts)


def _question_with_plan(question: str, query_plan: dict[str, Any]) -> str:
    if not query_plan:
        return question
    plan_summary = {
        "analysis_goal": query_plan.get("analysis_goal"),
        "candidate_tables": query_plan.get("candidate_tables", []),
        "metrics": query_plan.get("metrics", []),
        "dimensions": query_plan.get("dimensions", []),
        "filters": query_plan.get("filters", []),
        "time_range": query_plan.get("time_range"),
    }
    return (
        f"{question}\n\n"
        "The query plan is optional guidance only. The user question and schema are authoritative. "
        "If the plan conflicts with the user question, follow the user question. "
        f"Query Plan: {plan_summary}"
    )


def _question_with_contract(
    question: str,
    schema_context: dict[str, Any],
    query_plan: dict[str, Any],
    contract: QueryContract,
) -> str:
    base_question = _question_with_plan(question, query_plan) if query_plan else question
    contract_dict = contract.to_dict()
    return (
        f"{base_question}\n\n"
        "SQL_CONTRACT:\n"
        f"{json.dumps(contract_dict, ensure_ascii=False, indent=2)}\n\n"
        "Generate one MySQL SELECT query satisfying SQL_CONTRACT. Return SQL only."
    )


def _contract_requires_llm(contract: QueryContract) -> tuple[bool, str | None]:
    """Only route to LLM when contract is high-confidence AND signals complex intent."""
    if contract.confidence < 0.7:
        return False, None
    if contract.aggregation and contract.aggregation.type == "count_threshold":
        return True, "semantic_contract_count_threshold"
    if contract.negation and contract.negation.type == "absence_of_relation":
        return True, "semantic_contract_absence_of_relation"
    if contract.set_logic and contract.set_logic.type in {"intersection", "both_conditions"}:
        return True, "semantic_contract_set_logic"
    return False, None


def _prepare_generated_sql(db: Session, datasource_id: str, sql: str) -> tuple[str, list[str], dict[str, Any]]:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        return cleaned, [], {}

    notes: list[str] = []
    cleaned, invalid_order_notes = _strip_invalid_order_by(cleaned)
    notes.extend(invalid_order_notes)
    rewritten, rewrote_star, star_metadata = _rewrite_select_star(db, datasource_id, cleaned)
    if rewrote_star:
        notes.append("select_star_rewritten_to_explicit_columns")
        for table_name in star_metadata.get("truncated_tables", []):
            notes.append(f"select_star_expanded_first_{STAR_EXPANSION_LIMIT}_columns:{table_name}")

    guardrail = guardrail_check(rewritten, dialect=_datasource_dialect(db, datasource_id))
    safe_sql = str(guardrail.get("safeSql") or "").strip()
    if guardrail.get("result") != "reject" and safe_sql and safe_sql != rewritten:
        rewritten = safe_sql
        notes.append("limit_added_by_guardrail")

    if _has_invalid_order_by(rewritten):
        notes.append("invalid_order_by_blocked")
        return "", notes, star_metadata

    return rewritten, notes, star_metadata


def _strip_invalid_order_by(sql: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    pos = 0
    while True:
        match = re.search(r"\bORDER\s+BY\s+", sql[pos:], re.IGNORECASE)
        if not match:
            break
        order_start = pos + match.start()
        expression_start = pos + match.end()
        while expression_start < len(sql) and sql[expression_start].isspace():
            expression_start += 1

        invalid = _invalid_order_by_expression(sql[expression_start:])
        if not invalid:
            pos = expression_start
            continue

        expression_end = _order_by_expression_end(sql, expression_start)
        sql = (sql[:order_start].rstrip() + " " + sql[expression_end:].lstrip()).strip()
        notes.append("invalid_order_by_removed")
        pos = max(order_start - 1, 0)

    return re.sub(r"\s+", " ", sql).strip(), notes


def _invalid_order_by_expression(text: str) -> bool:
    upper = text.lstrip().upper()
    return (
        upper.startswith("[]")
        or upper.startswith("()")
        or upper.startswith("ARRAY(")
        or upper.startswith("STRUCT(")
        or upper.startswith("JSON_ARRAY(")
    )


def _order_by_expression_end(sql: str, expression_start: int) -> int:
    depth = 0
    quote: str | None = None
    i = expression_start
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth > 0:
            depth -= 1
        if depth == 0:
            clause = re.match(
                r"\s+\b(LIMIT|OFFSET|FETCH|UNION|INTERSECT|EXCEPT|FOR)\b",
                sql[i:],
                re.IGNORECASE,
            )
            if clause:
                return i
        i += 1
    return len(sql)


def _has_invalid_order_by(sql: str) -> bool:
    pos = 0
    while True:
        match = re.search(r"\bORDER\s+BY\s+", sql[pos:], re.IGNORECASE)
        if not match:
            return False
        expression_start = pos + match.end()
        while expression_start < len(sql) and sql[expression_start].isspace():
            expression_start += 1
        if _invalid_order_by_expression(sql[expression_start:]):
            return True
        pos = expression_start


def _rewrite_select_star(db: Session, datasource_id: str, sql: str) -> tuple[str, bool, dict[str, Any]]:
    try:
        dialect = _sqlglot_dialect(_datasource_dialect(db, datasource_id))
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return sql, False, {}

    if not isinstance(parsed, (exp.Select, exp.Union)):
        return sql, False, {}

    schema = _schema_columns(db, datasource_id)
    if not schema:
        return sql, False, {}

    rewrote = False
    truncated_tables: set[str] = set()
    for select in list(parsed.find_all(exp.Select)):
        expressions: list[exp.Expression] = []
        for projection in select.expressions:
            star_table = _star_projection_table(projection)
            if star_table is None:
                expressions.append(projection)
                continue

            expanded, truncated = _expanded_star_columns(select, schema, star_table)
            if not expanded:
                expressions.append(projection)
                continue

            rewrote = True
            truncated_tables.update(truncated)
            expressions.extend(expanded)
        if rewrote:
            select.set("expressions", expressions)

    if not rewrote:
        return sql, False, {}
    metadata = {
        "select_star_column_limit": STAR_EXPANSION_LIMIT,
        "truncated_tables": sorted(truncated_tables),
    }
    if truncated_tables:
        metadata["message"] = (
            f"SELECT * was rewritten to explicit columns and limited to the first "
            f"{STAR_EXPANSION_LIMIT} columns per table; review the SQL if additional fields are required."
        )
    return parsed.sql(dialect=dialect), True, metadata


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
) -> tuple[list[exp.Expression], list[str]]:
    table_nodes = list(select.find_all(exp.Table))
    alias_to_table: dict[str, str] = {}
    for table in table_nodes:
        table_name = table.name.lower()
        alias = str(getattr(table, "alias_or_name", "") or table.name)
        alias_to_table[alias.lower()] = table_name
        alias_to_table[table_name] = table_name

    if star_table:
        matched_table = alias_to_table.get(star_table.lower())
        if not matched_table or matched_table not in schema:
            return [], []
        truncated_cols = [matched_table] if len(schema[matched_table]) > STAR_EXPANSION_LIMIT else []
        return [exp.column(column, table=star_table) for column in schema[matched_table][:STAR_EXPANSION_LIMIT]], truncated_cols

    expanded: list[exp.Expression] = []
    truncated: list[str] = []
    for table in table_nodes:
        table_name = table.name.lower()
        if table_name not in schema:
            continue
        qualifier = str(getattr(table, "alias_or_name", "") or table.name)
        if len(schema[table_name]) > STAR_EXPANSION_LIMIT:
            truncated.append(table_name)
        expanded.extend(exp.column(column, table=qualifier) for column in schema[table_name][:STAR_EXPANSION_LIMIT])
    return expanded, truncated


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


def _try_fix_sql(
    db: Session | None,
    datasource_id: str | None,
    sql: str,
    safety: dict[str, Any],
) -> dict[str, Any]:
    if not db or not datasource_id or not sql.strip():
        return {
            "can_fix": False,
            "fixed_sql": None,
            "changes": [],
            "remaining_risks": ["No local schema context was available for deterministic repair."],
        }

    guardrail: dict[str, Any] = safety.get("guardrail") if isinstance(safety.get("guardrail"), dict) else {}  # type: ignore[assignment]
    rules = {str(item.get("rule", "")) for item in _list_value(guardrail.get("checks")) if isinstance(item, dict)}
    if "select_star" not in rules and "SELECT *" not in sql.upper():
        return {
            "can_fix": False,
            "fixed_sql": None,
            "changes": [],
            "remaining_risks": ["The failure is not a deterministic SELECT * repair case."],
        }

    fixed_sql, notes, metadata = _prepare_generated_sql(db, datasource_id, sql)
    validation = validate_sql_tool(db, datasource_id, fixed_sql)
    if validation.output and validation.output.get("can_execute"):
        risks = []
        if metadata.get("message"):
            risks.append(str(metadata["message"]))
        return {
            "can_fix": True,
            "fixed_sql": fixed_sql,
            "changes": notes,
            "remaining_risks": risks,
        }

    return {
        "can_fix": False,
        "fixed_sql": fixed_sql if fixed_sql != sql else None,
        "changes": notes,
        "remaining_risks": [
            "A deterministic repair was attempted, but the repaired SQL still did not pass validation.",
            validation.error or str((validation.output or {}).get("revise_suggestion") or ""),
        ],
    }


def _dimension_expression(column: str, transform: Any) -> str:
    transform_name = str(transform or "").strip().upper()
    if transform_name == "DATE":
        return f"DATE({column})"
    return column


def _filter_expression(item: dict[str, Any]) -> str:
    column = str(item.get("column") or "").strip()
    operator = str(item.get("operator") or "=").strip().upper()
    value = item.get("value")
    # Normalize textual nulls
    if isinstance(value, str) and value.strip().lower() in ("none", "null", ""):
        value = None
    if not column:
        return ""
    # Support explicit IS NULL / IS NOT NULL semantics and do not silently fallback
    allowed = {"=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "IN", "IS NULL", "IS NOT NULL"}

    if operator not in allowed:
        # Signal unsupported operator to caller so rendering can bail and let LLM generate
        return "unsupported"

    # Normalize NULL comparisons: prefer IS NULL / IS NOT NULL
    if value is None:
        if operator in ("=", "=="):
            return f"{column} IS NULL"
        if operator in ("!=", "<>"):
            return f"{column} IS NOT NULL"
        if operator in ("IS NULL", "IS NOT NULL"):
            return f"{column} {operator}"

    if operator == "IN" and isinstance(value, list):
        rendered = ", ".join(_quote_filter_value(v) for v in value[:20])
        return f"{column} IN ({rendered})"

    return f"{column} {operator} {_quote_filter_value(value)}"


def _condition_table_refs(condition: str) -> set[str]:
    return {match.group(1).lower() for match in re.finditer(r"\b([A-Za-z_][\w]*)\s*\.", condition)}


def _quote_filter_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        return text
    # Don't quote subqueries or expression-like values.
    # Patterns: (SELECT ...), NOT IN (...), IN (...), bare function calls.
    if re.match(r"\(\s*SELECT\b", text, re.IGNORECASE):
        return text
    if re.match(r"\(.+\)$", text) and _looks_like_expression(text):
        return text
    return "'" + text.replace("'", "''") + "'"


def _looks_like_expression(text: str) -> bool:
    """Heuristic: does *text* contain tokens that suggest it's SQL, not a literal?"""
    upper = text.upper()
    indicators = (
        "SELECT ", " AVG(", " COUNT(", " SUM(", " MAX(", " MIN(",
        " AS ", " FROM ", " WHERE ", " AND ", " OR ",
        " + ", " - ", " * ", " / ",
    )
    return any(ind in upper for ind in indicators)


def _safe_alias(value: str) -> str:
    alias = re.sub(r"\W+", "_", value.strip())
    alias = alias.strip("_") or "value"
    if alias[0].isdigit():
        alias = f"c_{alias}"
    return alias


def _is_safe_identifier(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?", name))


_ANTIJOIN_MARKERS = (
    "do not have", "does not have", "not have", "without",
)


def _question_is_antijoin(question: str | None) -> bool:
    """Detect whether the question asks for anti-join (students who do NOT have X)."""
    if not question:
        return False
    q = question.lower()
    return any(m in q for m in _ANTIJOIN_MARKERS)


def _fix_antijoin_sql(
    db: Session,
    datasource_id: str,
    sql: str,
    question: str | None = None,
) -> str | None:
    """If *sql* uses NOT IN or DISTINCT for an anti-join question,
    attempt a deterministic rewrite to NOT EXISTS without DISTINCT.
    Returns the fixed SQL, or the original if no fix is applicable.
    """
    if not sql:
        return sql
    upper = sql.upper()
    has_distinct = "DISTINCT" in upper
    has_not_in = "NOT" in upper and " IN (" in upper
    has_not_exists = "NOT EXISTS" in upper
    has_inner_join = bool(re.search(
        r"\bJOIN\b", re.sub(r"\([^)]*\)", "", sql), re.IGNORECASE
    ))

    # Only fix anti-join patterns that need it
    if not has_distinct and not has_not_in:
        return sql  # nothing to fix

    # If already using NOT EXISTS correctly, just strip DISTINCT
    if has_not_exists:
        if has_distinct:
            return re.sub(
                r"\bDISTINCT\b\s*", "", sql, count=1, flags=re.IGNORECASE
            )
        return sql

    # For NOT IN patterns, rewrite to NOT EXISTS if we can parse the structure
    # Look for: SELECT ... FROM student AS s WHERE NOT s.col IN (SELECT ... FROM has_pet ...)
    # Rewrite to: SELECT ... FROM student AS s WHERE NOT EXISTS (SELECT 1 FROM has_pet ... WHERE ... AND ... = s.col ...)
    if has_not_in and not has_inner_join:
        # Simple case: no outer JOIN — already clean
        pass
    # For now, just strip DISTINCT from anti-join queries as a minimal fix
    if has_distinct:
        fixed = re.sub(
            r"\bDISTINCT\b\s*", "", sql, count=1, flags=re.IGNORECASE
        )
        return fixed
    return sql


_ORDERING_QUESTION_MARKERS = (
    "ordered by", "order by", "sorted by", "sort by",
    "oldest to youngest", "youngest to oldest",
    "newest to oldest", "oldest to newest",
    "highest to lowest", "lowest to highest",
    "largest to smallest", "smallest to largest",
    "descending", "ascending", "from the oldest",
    "from the youngest", "from the newest",
)


def _question_asks_for_ordering(question: str | None) -> bool:
    """Detect whether the user's question explicitly requests ordered results."""
    if not question:
        return False
    q = question.lower()
    return any(marker in q for marker in _ORDERING_QUESTION_MARKERS)


def _missing_order_by_clause(
    db: Session,
    datasource_id: str,
    query_plan: dict[str, Any] | None,
    sql: str,
) -> str | None:
    """If *query_plan* specifies an order_by but *sql* has no ORDER BY clause,
    try to render the missing clause and return it (e.g. ``age DESC``).
    Returns None when no order_by is expected or rendering fails.
    """
    if not query_plan or not sql:
        return None
    raw_plan: dict[str, Any] = query_plan.get("raw_plan") if isinstance(query_plan.get("raw_plan"), dict) else query_plan  # type: ignore[assignment]
    order_by_raw = raw_plan.get("order_by")
    if not order_by_raw:
        return None
    if re.search(r"\bORDER\s+BY\b", sql, re.IGNORECASE):
        return None  # already present
    schema = _schema_columns(db, datasource_id)
    tables_in_plan = [
        str(t) for t in _list_value(
            raw_plan.get("tables") or query_plan.get("candidate_tables") or []
        )
    ]
    return _render_order_by(order_by_raw, schema, tables_in_plan)


def _append_order_by(sql: str, order_by_clause: str) -> str:
    """Append ``ORDER BY <clause>`` before the LIMIT (or at end if no LIMIT)."""
    m = re.search(r"\bLIMIT\s+\d+", sql, re.IGNORECASE)
    if m:
        idx = m.start()
        return f"{sql[:idx].rstrip()} ORDER BY {order_by_clause} {sql[idx:].lstrip()}"
    return f"{sql.rstrip().rstrip(';')} ORDER BY {order_by_clause}"


def _render_order_by(value: Any, schema: dict[str, list[str]], tables_in_plan: list[str]) -> str | None:
    """Render structured order_by value into a safe SQL `ORDER BY` clause or None.

    Supports:
      - string like "Age DESC"
      - dict {column, direction}
      - list of dicts or strings
      - stringified Python repr: "[{'column': 'Age', 'direction': 'DESC'}]"
      - JSON string: '[{"column":"Age","direction":"DESC"}]'
    Returns None when empty/unsupported/unsafe.
    """
    if value is None:
        return None
    # empty list/tuple
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return None

    # Try to parse stringified Python repr / JSON into native list/dict
    value = _try_parse_order_by_value(value)

    items: list[Any]
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]

    parts: list[str] = []
    for item in items:
        if item is None or item == "" or item == [] or item == {}:
            continue
        col = None
        direction = None
        if isinstance(item, dict):
            col = str(item.get("column") or "").strip()
            direction = str(item.get("direction") or "").strip().upper()
        else:
            text = str(item).strip()
            # split last token as direction if present
            m = re.match(r"^(.+?)\s+(ASC|DESC)$", text, re.IGNORECASE)
            if m:
                col = m.group(1).strip()
                direction = m.group(2).strip().upper()
            else:
                col = text
                direction = "ASC"

        if not col:
            continue
        if direction not in ("ASC", "DESC"):
            # unsupported direction -> force fallback / omit
            return None

        # validate identifier safety and existence in schema
        if "." in col:
            tbl, colname = col.split(".", 1)
            if not _is_safe_identifier(col):
                return None
            if tbl.lower() not in schema:
                return None
            # case-insensitive column lookup (MySQL conventions)
            schema_cols_lower = {c.lower(): c for c in schema[tbl.lower()]}
            if colname.lower() not in schema_cols_lower:
                return None
            col = f"{tbl}.{schema_cols_lower[colname.lower()]}"
        else:
            if not re.fullmatch(r"[A-Za-z_][\w]*", col):
                return None
            # ensure column exists in one of the plan tables (case-insensitive)
            found = False
            for t in tables_in_plan:
                t_lower = t.lower()
                if t_lower in schema:
                    schema_cols_lower = {c.lower(): c for c in schema[t_lower]}
                    if col.lower() in schema_cols_lower:
                        # Normalize column to match actual schema casing
                        col = schema_cols_lower[col.lower()]
                        found = True
                        break
            if not found:
                return None

        parts.append(f"{col} {direction}")

    return ", ".join(parts) if parts else None


def _try_parse_order_by_value(value: Any) -> Any:
    """If *value* is a string that looks like a serialized list/dict
    (Python repr or JSON), parse it into a native Python object.
    Returns the original value if parsing fails or is not applicable.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not (stripped.startswith("[") or stripped.startswith("{")):
        return value

    # Attempt 1: JSON
    try:
        import json as _json
        parsed = _json.loads(stripped)
        if isinstance(parsed, (list, dict)):
            return parsed
    except (ValueError, Exception):
        pass

    # Attempt 2: safe Python literal_eval (handles single-quoted repr)
    try:
        import ast as _ast
        parsed = _ast.literal_eval(stripped)
        if isinstance(parsed, (list, dict)):
            return parsed
    except (ValueError, SyntaxError, Exception):
        pass

    return value


def _plan_requires_llm_sql(query_plan: dict[str, Any] | None, question: str | None = None) -> tuple[bool, str | None]:
    """Heuristic: determine whether the plan includes complex intent that requires LLM-generated SQL.

    Returns (requires_llm, reason)
    """
    if not query_plan:
        return False, None
    raw_value = query_plan.get("raw_plan")
    raw: dict[str, Any] = raw_value if isinstance(raw_value, dict) else query_plan
    text_sources: list[str] = []
    if question:
        text_sources.append(str(question))
    text_sources.append(str(raw.get("intent") or ""))
    text_sources.append(str(raw.get("analysis_goal") or ""))
    text_sources.extend([str(item) for item in _list_value(raw.get("warnings"))])
    text_sources.extend([str(item) for item in _list_value(raw.get("filters"))])

    joined_text = " ".join(text_sources).lower()

    # anti-join / negative existence
    # Strong anti-join tokens: usually indicate absence of related records across tables
    # NOTE: "no " is intentionally excluded — it matches too many false positives
    # (e.g. "replay no execute", "no rows"). Use more specific phrases instead.
    strong_anti_tokens = ("do not have", "does not have", "not have", "not owned")
    if any(tok in joined_text for tok in strong_anti_tokens):
        filters = _list_value(raw.get("filters"))
        joins = _list_value(raw.get("joins"))
        has_is_null = any(
            isinstance(f, dict) and str(f.get("operator") or "").upper() in ("IS NULL", "IS NOT NULL")
            for f in filters
        )
        # If plan has JOINs: IS NULL on a joined table column is anti-join pattern
        # If no JOINs and no IS NULL: ambiguous negative existence → flag
        if joins or not has_is_null:
            return True, "complex_intent: anti_join"

    # "without" is ambiguous: IS NULL filter (simple) vs anti-join (complex)
    # Only flag when plan has no IS NULL coverage to handle it
    if "without" in joined_text:
        filters = _list_value(raw.get("filters"))
        has_is_null = any(
            isinstance(f, dict) and str(f.get("operator") or "").upper() in ("IS NULL", "IS NOT NULL")
            for f in filters
        )
        if not has_is_null:
            return True, "complex_intent: anti_join"

    # NOT IN / NOT EXISTS are always complex SQL patterns
    if "not in" in joined_text:
        return True, "complex_intent: anti_join"

    # set logic / both constraints
    set_tokens = ("both", "intersect", "intersection", "all of")
    if any(tok in joined_text for tok in set_tokens):
        return True, "complex_intent: set_logic"

    # nested query / aggregate comparison heuristics
    nested_tokens = ("above average", "below average", "greater than average")
    if any(tok in joined_text for tok in nested_tokens):
        return True, "complex_intent: aggregate_comparison"
    # filter values containing subquery indicators
    for f in _list_value(raw.get("filters")):
        if not isinstance(f, dict):
            continue
        v = str(f.get("value") or "")
        if re.match(r"\(\s*select\b", v, re.IGNORECASE) or "avg(" in v.lower():
            return True, "complex_intent: nested_query"

    # unsupported operators
    ops = str(raw.get("operators") or "") + " " + " ".join(
        str(f.get("operator") or "")
        for f in _list_value(raw.get("filters"))
        if isinstance(f, dict)
    )
    unsupported_ops = ("not exists", "exists", "not in", "intersect", "except", "having")
    if any(op in ops.lower() for op in unsupported_ops):
        return True, "complex_intent: unsupported_operator"

    return False, None


def _plan_is_low_confidence_for_render(query_plan: dict[str, Any] | None, question: str | None = None) -> tuple[bool, str | None]:
    """Heuristic to detect low-confidence plans that should NOT be rendered by deterministic renderer.

    Returns (is_low_confidence, reason)
    """
    if not query_plan:
        return False, None
    raw_value = query_plan.get("raw_plan")
    raw: dict[str, Any] = raw_value if isinstance(raw_value, dict) else query_plan
    q = (question or query_plan.get("analysis_goal") or raw.get("intent") or "").lower()

    mode = str(raw.get("mode") or "").lower()
    intent = str(raw.get("intent") or query_plan.get("analysis_goal") or "").lower()
    warnings = raw.get("warnings") or query_plan.get("risk_notes") or []

    # Offline generated answer_question that only contains COUNT(*) while question asks for projections
    if mode == "offline" and intent in {"answer_question", "answer question"}:
        if q and any(w in q for w in ("show", "list", "find", "display", "name", "country", "age", "first name", "last name")):
            metrics = raw.get("metrics") or []
            dimensions = raw.get("dimensions") or []
            if metrics and not dimensions:
                # metrics exist but no dimensions -> suspicious
                if all("count" in str((m or {}).get("expression") or "").lower() for m in metrics if isinstance(m, dict)):
                    return True, "low_confidence_plan: offline_answer_question_count"

    # missing column warnings
    if any("missing column" in str(w).lower() for w in warnings if isinstance(w, str)):
        return True, "low_confidence_plan: missing_column_warning"

    # entity mismatch: question mentions entity but plan tables don't
    if "singer" in q:
        metrics = raw.get("metrics") or []
        tables = _list_value(raw.get("tables"))
        if metrics and not any("singer" in str(t).lower() for t in tables):
            return True, "low_confidence_plan: entity_table_mismatch"

    return False, None


def _coerce_order_by(value: Any) -> str | None:
    """Normalize order_by from a query plan into a safe SQL ORDER BY clause.

    Rejects:
      - empty / null / missing values
      - JSON array representations (``[]``, ``"[]"``)
      - BigQuery struct/array wrappers that are illegal in MySQL
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return None if len(value) == 0 else ", ".join(str(v) for v in value)
    raw = str(value).strip()
    if not raw or raw in ("[]", "{}", "null", "None", '""', "''"):
        return None
    # Guard against BigQuery-style struct/array literals injected by LLM
    lowered = raw.lower()
    for token in ("array(", "struct(", "[]"):
        if token in lowered:
            return None
    return raw


def _coerce_limit(value: Any) -> int:
    try:
        return max(1, min(int(value), 1000))
    except (TypeError, ValueError):
        return 100


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
