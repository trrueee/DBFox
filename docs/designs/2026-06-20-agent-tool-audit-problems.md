# Agent Tool Audit Problem Report

> 2026-06-20 | audit of registered Agent tools, current failure modes, and cleanup direction

## 1. Scope

This document audits the currently registered DBFox Agent tools and the runtime/policy layer around them.

Current registered tools:

```text
control:
  escalate.tool_group

environment:
  environment.get_profile

schema:
  schema.list_tables
  schema.describe_table
  schema.refresh_catalog

db:
  db.observe
  db.search
  db.inspect
  db.preview
  db.query
  db.remember

result:
  result.profile

chart:
  chart.suggest

answer:
  answer.synthesize

memory:
  memory.search
  memory.write
  memory.delete
  memory.summarize_session
```

The review focuses on:

```text
1. tool size / context pressure
2. policy and approval correctness
3. repeated tool-call loops
4. state merge / checkpoint safety
5. legacy runtime bridges
6. product direction mismatch after removing metric rules and embedding recall
```

## 2. Executive Summary

The current tool layer has several systemic problems:

```text
1. db.query mixes validation, approval, and execution into one tool.
2. manual confirmation is produced by TrustGate but becomes tool failure instead of Agent approval.
3. db.search can loop because empty / failed / repeated results are treated as progress.
4. db.observe and environment/database map can generate very large state for large catalogs.
5. schema.list_tables returns all tables and is not paginated.
6. db.preview uses an old ToolContext / ToolObservation bridge under the new runtime.
7. db.remember and memory.write/delete are registered and exposed, but write tools are blocked by PolicyGate.
8. semantic alias / memory-oriented tools remain in the model-facing tool list even though the current product direction removed semantic alias / metric / embedding as main paths.
9. app service accumulated state appends routing lists instead of replacing them, causing stale allowed_tool_calls / last_tool_results risk.
10. tests cover idealized policy tools, not the actual active db.query / db.search / observe failure paths.
```

The short version:

```text
The Agent currently has too many broad tools, too little pagination, weak loop control, and unclear boundaries between deterministic tool execution, approval, and memory writes.
```

## 3. Runtime and Policy Layer Issues

### 3.1 PolicyGate Blocks Writes Unconditionally

PolicyGate blocks all tools whose policy side effect is `write` or `destructive`.

Impacted tools:

```text
db.remember
memory.write
memory.delete
```

Problem:

```text
These tools are still registered and exposed to the model via the memory/db groups, but PolicyGate blocks them.
```

Consequence:

```text
The model can call a tool that is advertised as available, then get blocked, then retry or choose another write-like path.
```

Recommended action:

```text
1. Do not expose write tools to the model by default.
2. If write tools are needed, route them through explicit approval flows.
3. Remove db.remember from the default Agent workflow until semantic memory is a confirmed product path.
```

### 3.2 allowed_tool_groups Are Too Broad

The service currently initializes the model with all safe groups:

```text
environment, schema, db, memory, result, chart, answer
```

Problem:

```text
The model sees too many tools at once, including memory tools and db.remember-like paths that are not stable product paths.
```

Consequence:

```text
The model can over-explore, use memory unnecessarily, or call tools that are policy-blocked.
```

Recommended action:

```text
Default groups should be minimal:
  environment, schema, db, answer

Enable result/chart only after successful query execution.
Enable memory only when explicitly requested or after user-confirmed memory workflows.
```

### 3.3 State Merge Uses Append Semantics for Routing Lists

The app service `_merge_state()` appends all list fields.

This is wrong for routing fields:

```text
allowed_tool_calls
blocked_tool_calls
pending_tool_calls
last_tool_results
allowed_tool_groups
```

Problem:

```text
A node returning allowed_tool_calls=[] may not clear the accumulated state.
```

Consequence:

```text
Frontend, checkpoint, and debug state can show stale tool calls, especially around approval resume.
```

Recommended action:

```text
Use replace semantics for routing lists.
Use append semantics only for event/history lists:
  messages
  trace_events
  runtime_events
  artifacts
  plan_events
  suggestions
  repair_trace
```

## 4. db.query Problems

### 4.1 db.query Has Too Many Responsibilities

Current `db.query` does all of this:

```text
1. accepts SQL from model
2. calls execute_query
3. runs TrustGate
4. handles safety decision internally
5. executes live data read
6. returns result rows
```

Problem:

```text
There is no clean insertion point for manual approval.
```

When TrustGate requires manual confirmation, it currently becomes:

```text
requires_confirmation -> blocked_reasons -> can_execute=false -> GuardrailValidationError -> tool failed
```

But it should become:

```text
requires_confirmation -> PolicyGate approval_required -> approval_node -> frontend confirmation
```

Recommended action:

```text
Replace model-facing db.query with:
  sql.validate
  sql.execute_readonly
```

### 4.2 db.query Does Not Use requires_validated_sql Policy

The active `DbQueryTool` policy is currently only:

```text
side_effect=read
risk_level=warning
```

It does not set:

```text
requires_validated_sql=True
```

Problem:

```text
The PolicyGate validated SQL rule is not applied to the active query tool.
```

Consequence:

```text
Policy tests can pass for a fake sql.execute_readonly tool while real db.query bypasses that pre-execution approval path.
```

Recommended action:

```text
1. Add sql.validate to produce state.safety.
2. Add sql.execute_readonly with requires_validated_sql=True.
3. Remove db.query from model-facing tools.
4. Keep db.query only as legacy/internal compatibility if needed.
```

### 4.3 Confirmation Rule Applies Beyond Prod

For `agent_readonly`, TrustGate requires confirmation when:

```text
env == prod OR risk_level == warning
```

Problem:

```text
Developers may expect confirmation only in prod, but warning SQL in non-prod can also require confirmation.
```

Recommended action:

```text
Document this product behavior clearly, or split policy:
  agent_readonly_prod_strict
  agent_readonly_dev_lenient
```

## 5. db.search Problems

### 5.1 db.search Is Not Recursive Internally, But Triggers ReAct Recursion

`db.search` itself only does:

```text
FTS search once
fallback keyword search once
return results
```

The recursive behavior comes from the Agent loop:

```text
db.search empty/weak result
  -> progress sees last_tool_results
  -> continue
  -> model calls db.search again
  -> repeat until max_steps
```

Problem:

```text
The progress node treats any tool observation as progress.
```

Recommended action:

```text
1. Track db.search query history.
2. Ban duplicate db.search with same query.
3. Allow at most two distinct search attempts per task unless new evidence appears.
4. If other schema evidence exists, ignore search failure and continue.
5. If search is empty twice and no evidence exists, ask user or finalize with a clear missing-schema message.
```

### 5.2 db.search Fallback Is Too Weak

When FTS returns nothing, fallback searches only:

```text
schema_tables.table_name
schema_tables.table_comment
schema_columns.column_name
schema_columns.column_comment
```

Problem:

```text
Fallback does not search ai_description, business_terms, semantic_tags, aliases, or schema_search_docs.search_text.
```

Consequence:

```text
If schema_search_docs/FTS is missing or stale, semantic search collapses to weak name/comment matching.
```

Recommended action:

```text
1. Make schema_search_docs the primary source even without FTS.
2. Fallback should search schema_search_docs fields via LIKE.
3. Include ai_description, business_terms, semantic_tags, aliases, and search_text.
4. Add telemetry when FTS is unavailable instead of silently swallowing exceptions.
```

### 5.3 db.search Is Treated as Required Instead of Optional

Problem:

```text
db.search failure can poison the run even when db.observe, schema.list_tables, or db.inspect already found the relevant table.
```

Recommended action:

```text
Treat db.search as a recall signal, not a gate.

If schema evidence exists:
  search failure = warning only
  do not call search again
```

## 6. db.observe Problems

### 6.1 db.observe Returns Full Catalog Summary

Current `db.observe` loads all catalog tables and builds schema/domain sections for all tables.

Problem:

```text
For 50 tables this is tolerable.
For thousands of tables this will create huge tool output and state.
```

It returns per-table summaries including:

```text
name
schema
type
comment
columns count
row_estimate
primary_key
tags
connected_tables
```

It also returns domains with full table name lists.

Consequence:

```text
1. large last_tool_results
2. large trace/output payloads
3. large checkpoint state
4. frontend context update pressure
5. potential prompt pressure if database_map or state is later rendered back to the model
```

Recommended action:

```text
Make db.observe lightweight only:
  datasource_id
  datasource_name
  dialect
  catalog_status
  table_count
  schema_count
  domain_count
  schema summaries
  domain summaries
  warnings
  next_action_hint
```

Do not return all table summaries from db.observe.

### 6.2 db.observe Should Be Paginated / Sampled

Recommended output for large catalogs:

```json
{
  "table_count": 3821,
  "large_catalog": true,
  "schemas": [
    {"name": "public", "table_count": 1800},
    {"name": "ods", "table_count": 1200}
  ],
  "domains": [
    {"name": "order", "table_count": 320, "sample_tables": ["orders", "order_items"]}
  ],
  "next_action_hint": "Use db.search or paginated schema.list_tables to find candidate tables."
}
```

### 6.3 db.observe Should Not Be Called Repeatedly

Recommended loop rule:

```text
db.observe can be called at most once per run unless catalog changed.
```

If `database_map` or `schema_evidence` already exists, repeated observe should be blocked by progress logic.

## 7. environment.get_profile Problems

### 7.1 database_map Build Path Appears Broken

`environment.get_profile` attempts to build a `database_map` and `database_map_summary`.

Problem:

```text
build_database_map() appears to instantiate EnvironmentService(db_session), but EnvironmentService is used elsewhere as EnvironmentService() and its methods expect db as the first argument.
```

This likely raises and gets swallowed by the broad exception handler.

Consequence:

```text
The database_map branch may silently fail, giving the impression that the Agent has a map when it does not.
```

Recommended action:

```text
1. Fix build_database_map API usage.
2. Add tests for environment.get_profile including database_map.
3. If database_map is retained, cap its size.
4. Do not include full database_map in tool output for large catalogs.
```

### 7.2 database_map Is Too Large by Design

`DatabaseMap` contains:

```text
all table profiles
all column profiles
relationships
semantic_index
sensitive columns
table_names
```

Problem:

```text
This is a world model, not a tool observation. It should not be returned whole to the Agent on every run.
```

Recommended action:

```text
Store database_map server-side or cache it separately.
Return only a compact summary to the model.
Expose targeted lookup tools for details.
```

## 8. schema.list_tables Problems

### 8.1 schema.list_tables Returns All Tables

Current `schema.list_tables` returns every table in the catalog.

Problem:

```text
This will explode for thousands of tables.
```

Recommended action:

```text
Add pagination and filters:
  schema
  domain
  query
  limit
  cursor
  include_comments
  include_counts
```

Default behavior:

```text
limit=50
include only table_name, schema, table_type, row_count_estimate, columns_count
```

### 8.2 schema.list_tables Auto-refreshes Catalog When Empty

If snapshot is empty, it automatically calls `ensure_catalog()`.

Problem:

```text
A read/list tool can trigger live introspection unexpectedly.
```

Consequence:

```text
On a large or slow datasource, a simple list call may become expensive or timeout.
```

Recommended action:

```text
Do not auto-refresh inside list_tables.
Return catalog_empty warning and ask Agent to call schema.refresh_catalog explicitly if needed.
```

## 9. schema.describe_table Problems

### 9.1 Exact Name Match Only

`schema.describe_table` looks up exact table_name.

Problem:

```text
No schema-qualified fallback, case-insensitive fallback, or candidate suggestions.
```

Consequence:

```text
Model can call describe_table with slightly wrong name, get failure, then loop.
```

Recommended action:

```text
1. Support schema.table.
2. Support case-insensitive exact match.
3. If not found, return candidate suggestions instead of raising.
4. Record not_found as non-useful evidence for loop control.
```

## 10. schema.refresh_catalog Problems

### 10.1 Expensive Tool Is Exposed Too Freely

`schema.refresh_catalog` can trigger live datasource introspection.

Problem:

```text
The model can call it when tables appear missing or stale, but on large databases it can be very expensive.
```

Recommended action:

```text
1. Require explicit user intent or approval for large/prod datasources.
2. Add dry-run estimate mode.
3. Add timeout and progress reporting.
4. Add table/schema filters.
```

## 11. db.inspect Problems

### 11.1 Live Introspection Can Be Expensive

`db.inspect` uses live database introspection and returns:

```text
columns
primary key
foreign_keys_out
foreign_keys_in
indexes
row_estimate
```

Problem:

```text
For wide tables or complex FK graphs, output can be large.
```

Recommended action:

```text
1. Add mode: summary | columns | relationships | indexes | full.
2. Default to summary.
3. Cap columns and indexes in model-facing output.
4. Keep full details as artifact/server-side state only when needed.
```

### 11.2 Missing Table Raises Error

If table is not found, `db.inspect` raises.

Problem:

```text
Tool failure can feed ReAct loops.
```

Recommended action:

```text
Return structured not_found output with candidate suggestions.
```

## 12. db.preview Problems

### 12.1 Mixed Old and New Tool Runtime

`DbPreviewTool` in the new registry delegates to `engine.tools.safe_preview.db_preview`, which wraps the older `engine.tools.db.preview.db_preview` using `ToolContext` and `ToolObservation`.

Problem:

```text
This creates two tool runtime styles in one tool path.
```

Consequence:

```text
Error shape, state shape, tracing, and output validation are harder to reason about.
```

Recommended action:

```text
Port db.preview fully to BaseTool / ToolRunContext.
Remove ToolContext / ToolObservation bridge.
```

### 12.2 Preview Executes Query Internally

`db.preview` builds SQL and calls `execute_query()` with policy `table_preview`.

This is okay in principle, but:

```text
1. it still reads live data
2. it returns rows into tool output
3. rows can increase state size
```

Recommended action:

```text
1. Keep max rows small.
2. Cap cell sizes in preview output.
3. Do not keep full preview rows in repeated state if not needed.
4. Make preview optional; do not force it before every query.
```

## 13. db.remember Problems

### 13.1 Product Direction Mismatch

Current product direction removed semantic alias / metric / embedding as main path.

But `db.remember` still writes to `SemanticAlias` for:

```text
table_alias
column_alias
column_values
join_path
business_definition
```

Problem:

```text
db.remember is semantically tied to the alias/memory direction that is no longer the primary product path.
```

Recommended action:

```text
Remove db.remember from default Agent tools.
Keep only behind explicit user-confirmed memory feature if needed.
```

### 13.2 Pending Confirmation Is Returned as Normal Tool Output

For prod or always-confirmed memory types, `db.remember` returns:

```text
status=pending_confirmation
```

Problem:

```text
This does not enter the Agent approval interrupt path.
```

Consequence:

```text
The model may think the memory was handled or may retry.
```

Recommended action:

```text
All user-confirmed writes must go through PolicyGate approval, not ad-hoc pending_confirmation outputs.
```

## 14. memory.* Problems

### 14.1 memory.write and memory.delete Are Exposed But Blocked

`memory.write` and `memory.delete` have write side effects.

PolicyGate blocks write tools.

Problem:

```text
The model can see and call tools that cannot execute.
```

Recommended action:

```text
1. Hide memory.write/delete from model by default.
2. Only expose memory.search by default if memory is retained.
3. Use explicit user action for memory writes/deletes.
```

### 14.2 memory.search Scope May Be Too Broad

`memory.search` defaults to user + datasource scopes.

Problem:

```text
It can pull unrelated prior context into a run.
```

Recommended action:

```text
1. Use memory.search only when the task asks for prior knowledge or when first-turn memory context is insufficient.
2. Add strict limit and type filters.
3. Do not encourage memory search in the default database workflow.
```

## 15. result.profile Problems

### 15.1 Profiles Returned Rows, Not Source Data

`result.profile` profiles only the rows returned to the Agent.

It already states this as a limitation, but the Agent can over-interpret.

Recommended action:

```text
1. Ensure answer.synthesize always includes the limitation.
2. For aggregate questions, prefer SQL aggregation over profiling sampled rows.
3. Do not call result.profile for simple count/detail lookups.
```

### 15.2 Result Profiling Can Add Noise

For small/simple results, profiling may add unnecessary steps and increase loop length.

Recommended action:

```text
Only call result.profile for analytical questions.
Progress logic should allow direct answer after simple successful execution.
```

## 16. chart.suggest Problems

### 16.1 Chart Tool Is Fine But Should Be Conditional

`chart.suggest` reads execution rows and suggests a chart.

Problem:

```text
If exposed too early, model can call it before execution and get failure.
```

Recommended action:

```text
Expose chart tools only after successful execution, or rely on PolicyGate/progress to prevent premature calls.
```

## 17. answer.synthesize Problems

### 17.1 Can Return Empty Answer If Called Too Early

If no execution and no error exist, `answer.synthesize` returns an empty answer.

Problem:

```text
The model can call answer.synthesize before enough evidence exists, producing poor finalization.
```

Recommended action:

```text
1. Policy/progress should only allow answer.synthesize when evidence exists.
2. If called too early, return structured not_ready instead of empty answer.
```

## 18. Tool Prompt Problems

### 18.1 Prompt Encourages Over-Search

Current prompt says:

```text
Search first.
Try multiple search terms before giving up.
Schema errors, unknown tables, empty results are YOUR problems to solve with tools.
```

Problem:

```text
This pushes the model toward repeated db.search and repeated schema exploration.
```

Recommended prompt change:

```text
Use db.search to find candidates, but do not repeat the same search.
If db.search returns no results once or twice, switch to db.observe or paginated schema.list_tables.
If another tool already identifies relevant tables, stop searching and proceed.
Ask the user only after limited exploration fails.
```

### 18.2 Prompt Still Mentions db.query as Main Tool

Current database workflow ends with `db.query`.

Recommended change:

```text
Replace db.query with:
  sql.validate
  sql.execute_readonly
```

## 19. Required Tool Contract Changes

### 19.1 Tool Output Size Classes

Every tool should declare output size class:

```text
small: safe for prompt/state
medium: summarized before prompt
large: artifact/server-side only, prompt receives summary
```

Recommended classifications:

```text
environment.get_profile: small
db.observe: small only
schema.list_tables: medium, paginated
schema.describe_table: medium
db.search: small/medium top-N
db.inspect: medium, mode-specific
db.preview: large artifact + small summary
db.query/sql.execute_readonly: large artifact + small summary
result.profile: medium
chart.suggest: medium
answer.synthesize: small
memory.search: small top-N
memory.write/delete/db.remember: hidden or approval-only
```

### 19.2 Useful Evidence Contract

Progress should understand whether a tool produced useful evidence.

Examples:

```text
db.search useful if results_count > 0
db.observe useful if it produced table_count/schema/domain summary
db.inspect useful if table exists and columns returned
schema.describe_table useful if table exists and columns returned
db.preview useful if rows or column summaries returned
db.query useful if execution success
sql.validate useful if safe_sql returned or hard blockers identified
result.profile useful if execution exists
answer.synthesize useful if answer non-empty
```

Empty, failed, or repeated tool calls should not count as progress.

## 20. Recommended New Tool Set

### Default Model-Facing Tools

```text
environment.get_profile
schema.list_tables_page
schema.describe_table
db.observe
db.search
db.inspect
sql.validate
sql.execute_readonly
answer.synthesize
```

### Conditional Tools

```text
db.preview          # only when data sample is needed
result.profile      # only after successful execution and analytical task
chart.suggest       # only after successful execution and visualization task
memory.search       # only when prior memory is relevant
```

### Hidden / Approval / Product-Later Tools

```text
db.remember
memory.write
memory.delete
schema.refresh_catalog
```

## 21. Recommended Implementation Phases

### Phase 1 — Stop the Bleeding

```text
1. Cap db.observe output.
2. Paginate schema.list_tables.
3. Add db.search duplicate / empty-result loop guard.
4. Fix service _merge_state replace semantics for routing lists.
5. Hide db.remember and memory.write/delete from default model-facing tools.
```

### Phase 2 — Fix SQL Approval Boundary

```text
1. Add sql.validate.
2. Add sql.execute_readonly.
3. Move manual confirmation into PolicyGate approval_required.
4. Remove db.query from model-facing tools.
5. Update prompt and tests.
```

### Phase 3 — Normalize Tool Runtime

```text
1. Port db.preview away from old ToolContext / ToolObservation bridge.
2. Ensure all tools return plain typed output through BaseTool.
3. Add output size caps and artifact summaries.
```

### Phase 4 — Large Catalog Readiness

```text
1. Make observe and list tools pagination-first.
2. Store large database_map server-side, return compact summaries only.
3. Add schema evidence state.
4. Make progress logic aware of schema evidence.
```

### Phase 5 — Product Cleanup

```text
1. Remove semantic alias / metric / embedding assumptions from tool descriptions.
2. Remove memory write paths unless product explicitly requires them.
3. Add clear user-confirmed memory UX if memory writes return.
```

## 22. Required Tests

### Runtime / Policy

```text
1. write tools are not exposed by default.
2. write tools route to approval if explicitly enabled.
3. allowed_tool_calls=[] clears accumulated state.
4. last_tool_results=[] clears accumulated state.
```

### db.search

```text
1. same db.search query cannot repeat.
2. two empty db.search attempts stop search path.
3. db.search failure is ignored if db.inspect/schema evidence exists.
4. fallback searches AI fields and schema_search_docs.
```

### db.observe / schema.list_tables

```text
1. db.observe caps output for >100 tables.
2. schema.list_tables defaults to limit=50.
3. list_tables does not auto-refresh catalog.
4. large catalog produces next_action_hint.
```

### SQL Approval

```text
1. sql.validate returns requires_confirmation without failing.
2. sql.execute_readonly with requires_confirmation returns approval_required.
3. approval resume executes safe_sql without re-triggering confirmation.
```

### Tool Runtime

```text
1. db.preview uses only BaseTool / ToolRunContext.
2. preview rows are capped and summarized.
3. result.profile is skipped for simple lookups.
4. answer.synthesize returns not_ready instead of empty answer when called early.
```

## 23. Final Recommendation

Do not keep adding prompt rules to fix tool behavior.

The tool layer needs hard contracts:

```text
1. small model-facing outputs
2. paginated catalog access
3. explicit validation/execution split
4. centralized approval
5. repeat-call loop guards
6. hidden write tools by default
7. schema evidence state to prevent search/observe loops
```

Until these are fixed, Agent behavior will remain unstable even if individual bugs are patched.
