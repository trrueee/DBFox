/** Human-readable display names for backend step / tool names. */
const STEP_DISPLAY: Record<string, string> = {
  // Schema / Environment
  "schema.build_context": "Understanding data structure",
  "schema.list_tables": "Listing available tables",
  "schema.describe_table": "Reading table schema",
  "schema.refresh_catalog": "Refreshing schema catalog",
  "build_schema_context": "Understanding data structure",
  "list_tables": "Listing available tables",
  "describe_table": "Reading table schema",
  "refresh_catalog": "Refreshing schema catalog",

  // Query planning
  "query_plan.build": "Planning query",
  "build_query_plan": "Planning query",

  // SQL lifecycle
  "sql.generate": "Generating SQL",
  "sql.validate": "Validating SQL safety",
  "sql.execute_readonly": "Executing query",
  "sql.skip_execution": "Skipping SQL execution",
  "sql.revise": "Revising SQL",
  "generate_sql_candidate": "Generating SQL",
  "validate_sql": "Validating SQL safety",
  "execute_sql": "Executing query",
  "revise_sql": "Revising SQL",

  // Results
  "result.profile": "Analyzing results",
  "profile_result": "Analyzing results",

  // Charts & Follow-ups
  "chart.suggest": "Suggesting chart",
  "suggest_chart": "Suggesting chart",
  "followup.suggest": "Suggesting follow-ups",
  "suggest_followups": "Suggesting follow-ups",
  "answer.synthesize": "Synthesizing answer",
  "answer_synthesizer": "Synthesizing answer",

  // Workspace
  "workspace.explain_sql": "Explaining SQL",
  "workspace.fix_sql": "Fixing SQL",
  "workspace.optimize_sql": "Optimizing SQL",
  "workspace.rewrite_sql": "Rewriting SQL",
  "workspace.explain_result": "Explaining result",
  "workspace.continue_from_artifact": "Continuing from artifact",
  "workspace.explain_schema": "Explaining workspace schema",

  // Memory
  "memory.search": "Searching memory",
  "memory.write": "Saving memory",
  "memory.delete": "Removing memory",
  "memory.summarize_session": "Summarizing session",
  "memory_search": "Searching memory",
  "memory_write": "Saving memory",
  "memory_delete": "Removing memory",
  "summarize_session": "Summarizing session",

  // Follow-up
  "followup.load_context": "Loading follow-up context",
  "load_follow_up_context": "Loading follow-up context",
};

export function stepDisplayName(toolName: string): string {
  return STEP_DISPLAY[toolName] || toolName;
}
