"""Clarification policy — coding-agent style: explore first, ask only when necessary."""

from __future__ import annotations

from typing import Any

from engine.agent.planning.schemas import AgentPlanDirective

# Reasons that must NOT trigger user interruption — agent should self-explore.
_SELF_RECOVERABLE_REASONS = frozenset({
    "unknown_table",
    "unknown_column",
    "sql_error",
    "empty_result",
    "unknown_join",
    "missing_schema",
})


def is_clarification_allowed(
    directive: AgentPlanDirective,
    state: dict[str, Any],
) -> tuple[bool, str]:
    """Return (allowed, reason) for planner-level clarification.

    Coding-agent rule: only interrupt when business ambiguity or risk requires
    a human decision. Schema/SQL exploration gaps are NOT clarification cases.
    """
    if not directive.needs_clarification:
        return False, "clarification_not_requested"

    question = (directive.clarification_question or "").lower()
    reasoning = (directive.reasoning_summary or "").lower()
    combined = f"{question} {reasoning}"

    if not state.get("datasource_id"):
        ws = state.get("workspace_context") or {}
        if not ws.get("active_table") and not ws.get("selected_sql"):
            return True, "no_datasource_and_no_workspace_anchor"

    if _is_missing_active_entity(directive, state):
        return True, "missing_necessary_entity"

    if _mentions_self_recoverable(combined):
        return False, "self_recoverable_gap"

    if _is_business_metric_ambiguity(directive, combined):
        return True, "business_metric_ambiguity"

    if directive.risk_notes and _needs_risk_confirmation(directive):
        return True, "high_risk_confirmation"

    # Default: suppress — let the agent explore schema/SQL first.
    return False, "explore_before_asking"


def should_progress_clarify(
    *,
    failure_layer: str | None,
    root_cause: str | None,
    progress_status: str,
) -> bool:
    """Gate progress-node clarify decisions against the same policy."""
    if progress_status != "clarify":
        return True

    combined = f"{failure_layer or ''} {root_cause or ''}".lower()
    if _mentions_self_recoverable(combined):
        return False
    if failure_layer in ("schema", "sql_generation", "sql_validation", "execution", "result_analysis"):
        return False
    if failure_layer == "semantic":
        return True
    return True


def _mentions_self_recoverable(text: str) -> bool:
    markers = (
        "table name", "table not found", "unknown table", "which table",
        "column", "field name", "unknown column", "not found",
        "sql error", "syntax error", "execute", "query failed",
        "empty result", "no rows", "no data",
        "join path", "how to join", "relationship",
        "should i query", "do you want me to", "shall i",
    )
    return any(m in text for m in markers)


def _is_missing_active_entity(directive: AgentPlanDirective, state: dict[str, Any]) -> bool:
    ws = state.get("workspace_context") or {}
    has_anchor = bool(
        ws.get("active_table")
        or ws.get("selected_sql")
        or ws.get("has_result")
    )
    if has_anchor:
        return False

    reasoning = (directive.reasoning_summary or "").lower()
    deictic = ("this table", "that table", "this query", "the table", "analyze this")
    return any(p in reasoning for p in deictic)


def _is_business_metric_ambiguity(directive: AgentPlanDirective, text: str) -> bool:
    if directive.task_type != "semantic_analysis":
        return False
    business_markers = (
        "active user", "dau", "mau", "retention", "churn",
        "revenue", "gmv", "conversion", "metric definition",
        "business definition", "which definition", "口径",
    )
    return any(m in text for m in business_markers)


def _needs_risk_confirmation(directive: AgentPlanDirective) -> bool:
    notes = " ".join(directive.risk_notes or []).lower()
    return any(w in notes for w in ("prod", "production", "destructive", "delete", "drop", "truncate"))
