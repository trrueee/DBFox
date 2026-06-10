from __future__ import annotations

from typing import Any

from engine.agent_contracts.tool_registry import ToolRegistry

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
        "List ALL tables in the current DATASOURCE (the live database). "
        "Use when the user asks \"what tables are available?\", \"有哪些表?\", "
        "or when schema.build_context returns zero tables. "
        "Outputs: table names, column counts, row estimates. "
        "Does NOT generate SQL. Does NOT require a workspace."
    ),
    "schema.describe_table": (
        "Describe a NAMED table from the live datasource: columns, types, "
        "keys, foreign keys, and sample rows. "
        "Use this when the user asks for the schema, columns, fields, or "
        "structure of a specific table (e.g. \"show me the singer table\", "
        "\"orders 表有哪些字段\", \"describe concert\"). "
        "Input: table_name. Outputs: column details, keys, sample data rows. "
        "This is the PRIMARY tool for table schema lookup."
    ),
    "schema.refresh_catalog": (
        "Re-introspect the live datasource and sync its schema to the DataBox "
        "catalog. Use when the catalog appears empty or stale (e.g., when "
        "schema.build_context or schema.list_tables returns zero results). "
        "Input: reason (optional). Outputs: sync counts. "
        "Side-effect: writes metadata to the system catalog (safe)."
    ),
    "environment.get_profile": (
        "Get the datasource environment profile: env tier (dev/staging/prod), "
        "dialect (mysql/postgres/sqlite/duckdb), catalog status (fresh/stale/empty), "
        "table count, and warnings. Use to understand the datasource environment "
        "before planning queries. No input required. Outputs: datasource_id, env, "
        "dialect, catalog_status, table_count, selected_tables, warnings."
    ),
    "semantic.resolve": (
        "Resolve business semantics for the current user question. "
        "Maps business terms (e.g. 'GMV', 'DAU'), metrics, dimensions, "
        "filters, and join paths to actual database objects. "
        "Use BEFORE sql.generate when the question contains business "
        "jargon or when you need to understand which tables/columns are "
        "relevant. Combines LLM understanding with catalog verification — "
        "tables and columns that don't exist are flagged as errors. "
        "Input: none required. Outputs: resolved_terms, resolved_metrics, "
        "resolved_dimensions, candidate_tables, join_paths, ambiguity, "
        "semantic_context_text."
    ),
    "memory.search": (
        "Search long-term memory for relevant context: user preferences, "
        "metric definitions, schema aliases, join paths, past successful "
        "queries, and lessons from failures. Use BEFORE planning a query "
        "to leverage past knowledge. Input: query, scope, memory_types."
    ),
    "memory.write": (
        "Write a new memory entry. Use when the user explicitly asks to "
        "remember something (e.g., \"记住销售额是 orders.total_amount\"). "
        "Input: type, text, content. Side-effect: writes to long-term store."
    ),
    "memory.delete": (
        "Delete a memory entry. Use when the user asks to forget or "
        "correct something. Input: memory_id, reason."
    ),
    "memory.summarize_session": (
        "Summarize the current session for future recall. "
        "Use at the end of an analysis session. Input: (none). "
        "Outputs: session summary with key findings and artifacts."
    ),
}

WORKSPACE_AFFORDANCE: dict[str, str] = {
    "workspace.explain_sql": (
        "Explain the SQL statement currently in the USER'S EDITOR. "
        "Only works when there is active SQL in the workspace editor. "
        "Do NOT use to explain SQL you just generated — use that result directly. "
        "Do NOT use to look up tables — use schema.describe_table instead."
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
        "Explain schema information already present in the CURRENT WORKSPACE "
        "CONTEXT, such as a selected schema artifact or prior schema-linking "
        "result. Only works when a workspace is active with selected tables. "
        "Do NOT use this tool to look up a table from the live datasource. "
        "If the user asks for the schema of a named table (e.g. \"show me "
        "the singer table\", \"orders 表结构\"), use schema_describe_table "
        "or schema_build_context instead."
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
