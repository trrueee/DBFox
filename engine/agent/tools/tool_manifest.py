from __future__ import annotations

from typing import Any

from engine.agent_core.tool_registry import ToolRegistry

# Enriched descriptions that give the LLM strong affordance hints.
TOOL_AFFORDANCE: dict[str, str] = {
    "schema.list_tables": (
        "List ALL tables in the current live datasource. "
        "Use when the user asks \"what tables are available?\" or "
        "db.observe returns zero tables. Outputs: table names, column counts, row estimates."
    ),
    "schema.describe_table": (
        "Describe a NAMED table from the live datasource: columns, types, keys, "
        "foreign keys. Input: table_name. Outputs: column details, keys."
    ),
    "schema.refresh_catalog": (
        "Re-introspect the live datasource and sync its schema to the DBFox "
        "catalog. Use when the catalog appears empty or stale."
    ),
    "db.observe": (
        "Look at the local database map: schemas, table summaries, domains, "
        "primary keys, foreign-key connections. Use to orient yourself before "
        "searching or querying. Does not read live rows."
    ),
    "db.search": (
        "Search the local database index for tables and columns by names, "
        "comments, aliases, and semantic synonyms. Use like grep: "
        "db.search('手机号 用户') returns candidates with scores and reasons. "
        "Follow with db.inspect or db.preview."
    ),
    "db.inspect": (
        "Inspect one live database object in real-time. Returns columns, primary "
        "keys, foreign keys (outbound + inbound), indexes, and row estimates. "
        "Use after db.search to verify candidate table structure."
    ),
    "db.preview": (
        "Preview a small masked sample from a table. Enforces LIMIT <= 20, "
        "TrustGate validation, timeout/truncation, and PII redaction. "
        "Use when sample values are needed to understand data shape."
    ),
    "db.query": (
        "Safely execute read-only SELECT SQL. Always re-validates inside the "
        "tool — do not assume prior validation is enough. Injects LIMIT when "
        "needed, blocks writes, masks sensitive values. Use when you have "
        "enough schema evidence to answer with data."
    ),
    "db.remember": (
        "Record business semantics or aliases for future database search. "
        "Use when the user asks to remember a table/column alias, metric "
        "definition, business rule, or join path."
    ),
    "environment.get_profile": (
        "Get the datasource environment profile: env tier, dialect, catalog "
        "status, table count, warnings. Use to understand the environment "
        "before planning queries."
    ),
    "semantic.resolve": (
        "Resolve business semantics for the current user question. "
        "Maps business terms (e.g. 'GMV', 'DAU'), metrics, dimensions, "
        "filters, and join paths to actual database objects."
    ),
    "memory.search": (
        "Search long-term memory for relevant context: user preferences, "
        "metric definitions, schema aliases, join paths, past queries."
    ),
    "memory.write": (
        "Write a new memory entry. Use when the user explicitly asks to "
        "remember something (e.g. \"记住销售额是 orders.total_amount\")."
    ),
    "memory.delete": (
        "Delete a memory entry. Use when the user asks to forget or correct "
        "something. Input: memory_id, reason."
    ),
    "memory.summarize_session": (
        "Summarize the current session for future recall."
    ),
    # Analysis tools
    "analyze_data": (
        "Compute a statistical profile of query execution results. Produces row count, "
        "column-level statistics (type, null ratio, min/max/avg, top values), detected "
        "patterns (time_series, category_breakdown, top_k, single_metric), notable "
        "facts, and anomalies. Call after db.query when results are too large or complex "
        "to analyze by inspection. Can be called with no arguments — auto-reads execution "
        "from state. Skip for simple lookups or single-value results."
    ),
    "chart.suggest": (
        "Suggest a chart type for the current query result. Analyzes column types "
        "(numeric, temporal, category) and data shape to recommend line, bar, area, "
        "scatter, or pie charts. Call after analyze_data when the result would benefit "
        "from visualization. Do not call for simple lookups or single-row results."
    ),

}



def enrich_description(name: str, raw_description: str) -> str:
    """Return an enriched tool description for the LLM."""
    affordance = TOOL_AFFORDANCE.get(name)
    if affordance:
        return affordance
    return raw_description


def get_tool_manifest(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Return list of serialized specs for all registered tools."""
    return [spec.model_dump() for spec in registry.list_specs()]
