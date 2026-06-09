from __future__ import annotations

from typing import Any

from engine.agent_kernel.tool_registry import ToolRegistry

# Enriched descriptions that give the LLM strong affordance hints.
# These are DataBox-specific guidance beyond the raw tool spec description.
TOOL_AFFORDANCE: dict[str, str] = {
    "followup.load_context": (
        "Load context from a previous agent run so the current question can build on "
        "prior SQL, results, and artifacts. Use this when the user references earlier work. "
        "Outputs: followup_context with context_summary, analysis_question, schema_linking_question."
    ),
    "schema.build_context": (
        "Discover relevant tables and columns for a data question. "
        "Use this FIRST when table/column context is uncertain. "
        "Outputs: schema_context (DDL snippet), selected_tables, candidate_columns. "
        "Does NOT generate SQL. After this, use query_plan.build or sql.generate."
    ),
    "query_plan.build": (
        "Build a structured query plan (metrics, dimensions, filters, time_range, candidate_tables). "
        "Use this AFTER schema.build_context when the question involves aggregations, groupings, "
        "filters, joins, or time-series analysis. Outputs: query_plan dict. Does NOT generate SQL."
    ),
    "sql.generate": (
        "Generate a SQL candidate from schema_context and/or query_plan. "
        "Use this AFTER schema context is available. Prefer providing query_plan when available. "
        "Outputs: sql candidate (NOT executed). Does NOT validate. Must be followed by sql.validate."
    ),
    "sql.validate": (
        "Validate a SQL candidate through TrustGate and guardrail checks. "
        "MUST be called before sql.execute_readonly. "
        "Outputs: safety dict with can_execute, safe_sql, blocked_reasons, requires_confirmation."
    ),
    "sql.execute_readonly": (
        "Execute a validated read-only SQL query against the datasource. "
        "ONLY call after sql.validate succeeds and returns can_execute=true. "
        "Do NOT call if execution is disabled. Outputs: execution result with columns, rows, rowCount."
    ),
    "sql.skip_execution": (
        "Record that SQL execution was intentionally skipped (review-only mode). "
        "Use when execute=false in the request. Outputs: skip confirmation."
    ),
    "sql.revise": (
        "Revise a SQL query that failed validation or execution. "
        "Use when sql.validate or sql.execute_readonly returns errors. "
        "Outputs: revised SQL candidate (can_fix=True) OR stop signal (can_fix=False). "
        "If can_fix=False, do NOT call sql.revise again — the SQL cannot be "
        "automatically fixed. Instead, generate a new SQL with sql.generate "
        "or explain the problem to the user and finalize."
    ),
    "result.profile": (
        "Profile query execution results to detect patterns, anomalies, and notable facts. "
        "Use AFTER successful sql.execute_readonly. Outputs: result_profile with row_count, "
        "column_profiles, notable_facts, anomalies."
    ),
    "chart.suggest": (
        "Suggest a chart type and axis encoding based on execution result columns. "
        "Use AFTER result.profile when visualization would help. Outputs: chart_suggestion."
    ),
    "followup.suggest": (
        "Suggest evidence-aware follow-up questions based on the current analysis. "
        "Outputs: list of follow-up suggestions."
    ),
    "answer.synthesize": (
        "Synthesize a final, evidence-grounded answer from all tool results. "
        "Use when enough information is available to answer the user's question. "
        "After this, do NOT call more tools — you are done."
    ),
    "schema.list_tables": (
        "List all known tables in the current datasource's schema catalog. "
        "Use when schema.build_context returns zero tables, or when you need "
        "to discover what tables are available. Outputs: table names, column "
        "counts, row estimates. Does NOT generate SQL."
    ),
    "schema.describe_table": (
        "Describe a specific table: columns, types, keys, and sample rows. "
        "Use when you need to understand the structure of a particular table "
        "before writing queries. Input: table_name. "
        "Outputs: column details and sample data rows."
    ),
    "schema.refresh_catalog": (
        "Re-introspect the live datasource and sync its schema to the DataBox "
        "catalog. Use when the catalog appears empty or stale (e.g., when "
        "schema.build_context or schema.list_tables returns zero results). "
        "Input: reason (optional). Outputs: sync counts. "
        "Side-effect: writes metadata to the system catalog (safe)."
    ),
}

WORKSPACE_AFFORDANCE: dict[str, str] = {
    "workspace.explain_sql": (
        "Explain an existing SQL statement in the editor. "
        "Operates on the user's current editor SQL. Does NOT generate or execute new SQL."
    ),
    "workspace.fix_sql": (
        "Fix errors in the user's existing editor SQL. "
        "Use when the user reports an error. Does NOT execute SQL."
    ),
    "workspace.optimize_sql": (
        "Optimize the user's editor SQL for performance. Does NOT execute SQL."
    ),
    "workspace.rewrite_sql": (
        "Rewrite the user's editor SQL per their instructions. Does NOT execute SQL."
    ),
    "workspace.explain_result": (
        "Explain the result set currently visible in the editor. "
        "Uses the last query result preview. Does NOT execute new SQL."
    ),
    "workspace.continue_from_artifact": (
        "Continue analysis from a previously generated artifact. "
        "Uses the selected artifact as context."
    ),
    "workspace.explain_schema": (
        "Explain the schema/structure of selected tables. Does NOT execute SQL."
    ),
}


def enrich_description(name: str, raw_description: str) -> str:
    """Return an enriched tool description for the LLM.

    Uses DataBox-specific affordance hints when available,
    falling back to the raw spec description.
    """
    affordance = TOOL_AFFORDANCE.get(name) or WORKSPACE_AFFORDANCE.get(name)
    if affordance:
        return affordance
    return raw_description


def get_tool_manifest(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Return list of serialized specs for all registered tools."""
    return [spec.model_dump() for spec in registry.list_specs()]
