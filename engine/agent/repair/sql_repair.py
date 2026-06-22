"""Structured SQL repair loop — coding-agent style error classification and recovery."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SqlErrorClass = Literal[
    "syntax_error",
    "missing_table",
    "missing_column",
    "ambiguous_column",
    "type_mismatch",
    "permission_denied",
    "timeout",
    "empty_result",
    "validation_blocked",
    "unknown",
]

_MAX_REPAIR_ATTEMPTS = 3


class SqlRepairPlan(BaseModel):
    """Recovery plan produced by the SQL repair classifier."""

    error_class: SqlErrorClass
    failure_layer: str
    root_cause: str
    recovery_strategy: str
    next_action_hint: str
    user_visible_update: str
    next_tool_groups: list[str] = Field(default_factory=list)
    retry_budget: int = 0
    should_retry: bool = False


def classify_sql_failure(
    *,
    error_text: str,
    execution: dict[str, Any] | None = None,
    safety: dict[str, Any] | None = None,
) -> SqlErrorClass:
    """Map error text to a structured repair category."""
    execution = execution or {}
    safety = safety or {}
    el = error_text.lower()

    if execution.get("success") and int(execution.get("rowCount") or 0) == 0:
        return "empty_result"

    if any(k in el for k in ("permission", "denied", "access", "not authorized")):
        return "permission_denied"
    if "timeout" in el or "timed out" in el:
        return "timeout"
    if "ambiguous" in el and "column" in el:
        return "ambiguous_column"
    if any(k in el for k in ("syntax", "parse error", "near", "unexpected")):
        return "syntax_error"
    if any(k in el for k in ("column", "field", "attribute", "unknown column")):
        return "missing_column"
    if any(k in el for k in ("table", "relation", "unknown table", "does not exist")):
        return "missing_table"
    if any(k in el for k in ("type", "cast", "cannot convert", "incompatible")):
        return "type_mismatch"
    if safety.get("blocked_reasons") or any(k in el for k in ("guardrail", "trust gate", "validation", "blocked")):
        return "validation_blocked"
    return "unknown"


def plan_sql_repair(
    state: dict[str, Any],
    *,
    error_text: str | None = None,
) -> SqlRepairPlan | None:
    """Build a repair plan when SQL/execution failed. Returns None when budget exhausted."""
    revision_count = int(state.get("revision_count") or 0)
    if revision_count >= _MAX_REPAIR_ATTEMPTS:
        return None

    execution = state.get("execution") or {}
    safety = state.get("safety") or {}

    if not error_text:
        if isinstance(safety.get("blocked_reasons"), list) and safety["blocked_reasons"]:
            error_text = "; ".join(str(r) for r in safety["blocked_reasons"])
        else:
            error_text = str(execution.get("error") or state.get("error") or "")

    if execution.get("success") and int(execution.get("rowCount") or 0) == 0:
        error_text = error_text or "Query succeeded but returned zero rows."

    if not error_text:
        return None

    error_class = classify_sql_failure(
        error_text=error_text,
        execution=execution,
        safety=safety,
    )
    budget = max(0, _MAX_REPAIR_ATTEMPTS - revision_count - 1)

    plans: dict[SqlErrorClass, SqlRepairPlan] = {
        "empty_result": SqlRepairPlan(
            error_class="empty_result",
            failure_layer="result_analysis",
            root_cause=error_text[:300],
            recovery_strategy="Check whether filters are too strict; widen time range or sample data.",
            next_action_hint="Relax filters or verify date range, then re-run a broader query.",
            user_visible_update="Query returned no rows — checking whether filters are too strict.",
            next_tool_groups=["sql_repair", "sql_generation", "execution"],
            retry_budget=budget,
        ),
        "missing_column": SqlRepairPlan(
            error_class="missing_column",
            failure_layer="schema",
            root_cause=error_text[:300],
            recovery_strategy="Use schema.describe_table and fuzzy-match similar columns, then sql.revise.",
            next_action_hint="Re-check schema for the correct column name and revise SQL.",
            user_visible_update="Column not found — looking up schema to fix the query.",
            next_tool_groups=["schema", "sql_repair", "sql_validation"],
            retry_budget=budget,
        ),
        "missing_table": SqlRepairPlan(
            error_class="missing_table",
            failure_layer="schema",
            root_cause=error_text[:300],
            recovery_strategy="Use schema.list_tables to find the correct table, then rebuild SQL.",
            next_action_hint="Search schema for the correct table name and rebuild the query.",
            user_visible_update="Table not found — searching schema for matching tables.",
            next_tool_groups=["schema", "sql_generation", "sql_repair"],
            retry_budget=budget,
        ),
        "ambiguous_column": SqlRepairPlan(
            error_class="ambiguous_column",
            failure_layer="sql_generation",
            root_cause=error_text[:300],
            recovery_strategy="Add table aliases to disambiguate columns, then sql.revise.",
            next_action_hint="Add table qualifiers to ambiguous columns and revise SQL.",
            user_visible_update="Ambiguous column — adding table qualifiers to fix SQL.",
            next_tool_groups=["sql_repair", "sql_validation", "execution"],
            retry_budget=budget,
            should_retry=True,
        ),
        "syntax_error": SqlRepairPlan(
            error_class="syntax_error",
            failure_layer="sql_generation",
            root_cause=error_text[:300],
            recovery_strategy="Fix SQL syntax via sql.revise using the error message.",
            next_action_hint="Revise SQL to fix syntax error.",
            user_visible_update="SQL syntax error — revising the query.",
            next_tool_groups=["sql_repair", "sql_validation", "execution"],
            retry_budget=budget,
            should_retry=True,
        ),
        "type_mismatch": SqlRepairPlan(
            error_class="type_mismatch",
            failure_layer="sql_generation",
            root_cause=error_text[:300],
            recovery_strategy="Cast operands or adjust filter types, then sql.revise.",
            next_action_hint="Fix type mismatch with CAST or adjusted filters.",
            user_visible_update="Type mismatch — adjusting SQL casts and filters.",
            next_tool_groups=["sql_repair", "sql_validation", "execution"],
            retry_budget=budget,
            should_retry=True,
        ),
        "timeout": SqlRepairPlan(
            error_class="timeout",
            failure_layer="execution",
            root_cause=error_text[:300],
            recovery_strategy="Simplify query or add LIMIT, then retry once.",
            next_action_hint="Simplify the query and retry with a smaller scope.",
            user_visible_update="Query timed out — simplifying and retrying.",
            next_tool_groups=["sql_repair", "execution"],
            retry_budget=budget,
            should_retry=True,
        ),
        "validation_blocked": SqlRepairPlan(
            error_class="validation_blocked",
            failure_layer="sql_validation",
            root_cause=error_text[:300],
            recovery_strategy="Use sql.revise to fix validation issues, then re-validate.",
            next_action_hint="Revise SQL to pass guardrail validation.",
            user_visible_update="SQL validation failed — fixing safety issues.",
            next_tool_groups=["sql_repair", "sql_validation"],
            retry_budget=budget if revision_count < 2 else 0,
            should_retry=revision_count < 2,
        ),
        "permission_denied": SqlRepairPlan(
            error_class="permission_denied",
            failure_layer="execution",
            root_cause=error_text[:300],
            recovery_strategy="Cannot auto-repair permission errors; explain and suggest read-only alternative.",
            next_action_hint="Report permission error; do not retry destructive paths.",
            user_visible_update="Permission denied — cannot execute this query.",
            next_tool_groups=["answer"],
            retry_budget=0,
        ),
        "unknown": SqlRepairPlan(
            error_class="unknown",
            failure_layer="execution",
            root_cause=error_text[:300],
            recovery_strategy="Use sql.revise with the execution error, re-validate, then retry.",
            next_action_hint="Revise SQL based on the execution error.",
            user_visible_update="Query failed — revising SQL based on the error.",
            next_tool_groups=["sql_repair", "sql_validation", "execution"],
            retry_budget=budget,
            should_retry=True,
        ),
    }

    plan = plans.get(error_class)
    if plan is None:
        return None
    if plan.error_class == "permission_denied":
        return plan
    return plan


def repair_plan_to_progress_decision(plan: SqlRepairPlan) -> dict[str, Any]:
    """Convert SqlRepairPlan to progress_decision dict."""
    from engine.agent.progress.schemas import ProgressDecision

    decision = ProgressDecision(
        status="continue",
        reason_summary=plan.recovery_strategy,
        failure_layer=plan.failure_layer,  # type: ignore[arg-type]
        root_cause=plan.root_cause,
        recovery_strategy=plan.recovery_strategy,
        next_action_hint=plan.next_action_hint,
        user_visible_update=plan.user_visible_update,
        next_tool_groups=plan.next_tool_groups,
        retry_budget=plan.retry_budget,
        should_retry=plan.should_retry,
    )
    return decision.model_dump(mode="json")


def _first_text_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _failed_sql_from_state(state: dict[str, Any] | None) -> str:
    if not state:
        return ""

    failed_sql = _first_text_value(state, ("sql", "current_sql", "generated_sql"))
    if failed_sql:
        return failed_sql

    for nested_key in ("safety", "execution"):
        nested = state.get(nested_key)
        if not isinstance(nested, dict):
            continue
        failed_sql = _first_text_value(
            nested,
            ("safe_sql", "sql", "executed_sql", "query_sql", "original_sql"),
        )
        if failed_sql:
            return failed_sql

    return ""


def build_repair_trace_event(
    plan: SqlRepairPlan,
    attempt: int,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "type": "agent.repair.attempted",
        "attempt": attempt,
        "error_class": plan.error_class,
        "failure_layer": plan.failure_layer,
        "root_cause": plan.root_cause,
        "recovery_strategy": plan.recovery_strategy,
        "user_visible_update": plan.user_visible_update,
        "next_tool_groups": plan.next_tool_groups,
    }
    failed_sql = _failed_sql_from_state(state)
    if failed_sql:
        event["failed_sql"] = failed_sql
    return event
