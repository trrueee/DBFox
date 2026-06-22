# Broader Code Quality Audit Problem Report

> 2026-06-20 | non-tool code quality issues affecting the minimum reliable product loop

## 1. Scope

This document covers code quality and architecture issues outside the Agent tool audit itself.

It focuses on the parts that affect the minimum reliable DBFox loop:

```text
connect datasource
  -> sync schema
  -> optionally AI-enrich table/column descriptions
  -> build schema_search_docs
  -> search relevant schema
  -> generate safe SQL
  -> validate / approve / execute
  -> return result
```

Out of scope for the current minimum loop:

```text
semantic metric rules
semantic aliases as main product path
embedding recall
complex long-term memory writes
automatic charting as required flow
full database world model in prompt
```

## 2. Executive Summary

The codebase is not fundamentally unusable, but it is currently in a feature-accumulation phase rather than a stable product-loop phase.

The main quality issue is not one bug. It is architectural drift:

```text
1. multiple schema sync paths
2. schema sync and AI enrich coupled too tightly
3. schema_search_docs not treated as reliable infrastructure
4. large catalog support missing
5. old and new runtime abstractions mixed
6. semantic/memory features still leaking into the core path
7. tests validate idealized paths instead of real failure paths
8. frontend workflows trigger expensive backend work by default
9. errors are often swallowed or downgraded without telemetry
```

The recommended direction is to stop expanding features and stabilize the minimum loop.

## 3. Priority Ranking

### P0 — Must fix for minimum reliable loop

```text
1. Split schema sync from AI enrich.
2. Consolidate schema sync entry points.
3. Make schema_search_docs deterministic and always rebuildable.
4. Add large catalog limits to observe/list/search outputs.
5. Split SQL validation from execution.
6. Add search/observe/list loop guards.
```

### P1 — Important cleanup

```text
1. Remove semantic alias / metric / embedding from the core path.
2. Normalize tool runtime abstractions.
3. Improve tests around failure and edge cases.
4. Add telemetry for fallback/error paths.
5. Fix frontend default flow and request cancellation.
```

### P2 — Later product maturity

```text
1. DatabaseMap as server-side cache, not model prompt payload.
2. Chart/result profile polish.
3. Long-term memory workflows with explicit user approval.
4. Background jobs and progress UI for expensive operations.
```

## 4. Schema Sync Architecture Problems

### 4.1 There Are Multiple Schema Sync Paths

Current codebase has at least two schema sync implementations:

```text
engine/schema_sync.py
engine/environment/schema_catalog_sync.py
```

Problem:

```text
API/UI datasource sync and Agent environment catalog sync can go through different code paths.
```

Likely consequences:

```text
1. UI may see one schema state.
2. Agent may see another schema state.
3. schema_search_docs may be rebuilt from only one path.
4. Bugs fixed in one sync implementation may not fix the other.
5. Tests can pass for one path while product uses another.
```

Minimum-loop requirement:

```text
There must be one canonical schema catalog sync path.
```

Recommended action:

```text
1. Pick one canonical implementation.
2. Make /datasources/{id}/sync and Agent schema refresh call the same implementation.
3. Mark the older implementation as legacy or remove it after migration.
4. Add one integration test that goes through the public API and then verifies Agent tools see the same catalog.
```

### 4.2 Sync Should Not Auto-Trigger AI Enrich

Current behavior can make datasource creation or schema sync trigger AI enrich implicitly.

Problem:

```text
Schema sync should be fast, deterministic, and independent of LLM availability.
```

Coupling schema sync with LLM enrich causes:

```text
1. datasource creation feels slow or stuck
2. sync can fail due to API key/model/LLM output issues
3. large schemas can blow context or token budgets
4. retries are ambiguous: is schema sync failing, or AI enrich failing?
```

Minimum-loop requirement:

```text
POST /datasources/{id}/sync
  -> only introspect and persist schema catalog
  -> build base schema_search_docs
  -> return quickly

POST /datasources/{id}/ai-enrich
  -> optional, separate operation
  -> updates AI fields
  -> rebuilds affected schema_search_docs
```

Recommended action:

```text
1. Default ai_enrich=false for schema sync.
2. Add separate endpoint/action for AI enrich.
3. Frontend should expose AI enrich as an explicit button or job.
4. UI copy should distinguish "Sync schema" from "AI enrich descriptions".
```

## 5. AI Enrichment Problems

### 5.1 AI Enrich Is Too Coupled to Search Index Generation

AI enrich currently updates table/column AI fields and rebuilds schema_search_docs on its success path.

Problem:

```text
schema_search_docs should exist even when AI enrich is disabled, missing an API key, or fails.
```

Minimum-loop requirement:

```text
Base search docs must be generated from raw schema metadata.
AI enrich should improve docs, not decide whether docs exist.
```

Recommended behavior:

```text
schema sync:
  schema_tables/schema_columns updated
  base schema_search_docs rebuilt

AI enrich:
  AI fields updated
  affected schema_search_docs rebuilt with richer text
```

### 5.2 AI Enrich Batch Failure Can Make Search Stale

If an AI enrich batch fails, current behavior can leave search docs missing or stale for affected tables.

Recommended action:

```text
1. Treat AI enrich as best-effort enhancement.
2. Keep base docs even if enrich fails.
3. Store enrich status per table/batch.
4. Report failed table names and retryability clearly.
5. Never rollback base schema catalog due to AI enrich failure.
```

### 5.3 AI Enrich Prompt/Output Validation Is Fragile

Batch enrichment requires the LLM to return expected table outputs.

Problem:

```text
If one table is missing or output shape is invalid, the whole batch may fail.
```

Recommended action:

```text
1. Use smaller batches for large schemas.
2. Accept partial valid output where possible.
3. Mark missing tables as enrich_failed, not sync_failed.
4. Add retry per failed table/batch.
```

## 6. schema_search_docs Problems

### 6.1 schema_search_docs Is Not a First-Class Infrastructure Table Yet

Current direction keeps schema_search_docs, but the implementation still treats it like an AI-enrich side effect.

Problem:

```text
db.search depends on schema_search_docs / FTS, but docs are not reliably produced by every metadata mutation.
```

Required invariant:

```text
For every SchemaTable and SchemaColumn, there should be corresponding searchable document rows unless explicitly excluded.
```

Recommended action:

```text
1. Add rebuild_search_docs_for_datasource(datasource_id).
2. Add rebuild_search_docs_for_table(datasource_id, table_id).
3. Call rebuild after schema sync.
4. Call rebuild after AI enrich.
5. Call rebuild after manual table/column metadata edit.
6. Add health check: schema tables count vs search docs count.
```

### 6.2 Manual Metadata Updates Do Not Rebuild Search Docs

Manual edits to table/column descriptions should affect search.

Problem:

```text
If user edits table_comment or column_comment, schema_search_docs may stay stale.
```

Recommended action:

```text
1. Metadata update APIs must rebuild docs for the affected table.
2. Tests should verify db.search finds newly edited descriptions.
```

### 6.3 FTS Fallback Is Too Weak

When FTS is unavailable, db.search fallback should not collapse to only name/comment matching.

Recommended fallback search should include:

```text
schema_search_docs.name
schema_search_docs.search_text
schema_search_docs.ai_description
schema_search_docs.business_terms
schema_search_docs.semantic_tags
schema_search_docs.aliases
schema_tables.table_name/table_comment
schema_columns.column_name/column_comment
```

### 6.4 FTS Failure Is Too Quiet

Current FTS exceptions can be swallowed and fallback used silently.

Problem:

```text
Developers cannot tell whether search failed because docs are empty, FTS table is missing, MATCH syntax failed, or fallback simply found nothing.
```

Recommended telemetry:

```text
search_engine_requested=fts5
search_engine_used=fts5 | docs_like | keyword_fallback
fts_error_type
fts_error_message_debug
search_docs_count
fts_index_count
fallback_used
results_count
```

## 7. Large Catalog Readiness Problems

### 7.1 db.observe Returns Too Much

Current db.observe can return a database map with all schema sections and all table summaries.

Problem:

```text
This is acceptable for dozens of tables but unsafe for thousands.
```

Failure modes:

```text
1. last_tool_results becomes huge
2. checkpoint state becomes huge
3. frontend context update becomes huge
4. model prompt can indirectly receive too much if summaries are rendered later
5. state merge and persistence slow down
```

Recommended action:

```text
db.observe should return only lightweight overview:
  datasource name
  dialect
  catalog status
  table_count
  schema_count
  domain_count
  top schemas/domains by count
  warnings
  next_action_hint
```

Do not return full table lists or connected table lists from db.observe.

### 7.2 schema.list_tables Is Not Paginated

Current list tables returns every table.

Problem:

```text
For thousands of tables, this is not a tool output; it is an export.
```

Recommended replacement:

```text
schema.list_tables_page(
  schema?: str,
  query?: str,
  domain?: str,
  limit: int = 50,
  cursor?: str,
  include_comments: bool = false
)
```

### 7.3 database_map Is Too Large to Return Whole

DatabaseMap contains all table profiles, all columns, relationships, semantic index, sensitive columns, and table names.

Problem:

```text
This should be a server-side cache / index, not a model-facing payload.
```

Recommended action:

```text
1. Store DatabaseMap server-side if retained.
2. Return only compact summary to model.
3. Use targeted lookup tools for details.
4. Do not put full database_map into environment.get_profile output.
```

## 8. Runtime Abstraction Problems

### 8.1 Old and New Tool Runtime Are Mixed

Example: db.preview uses a new BaseTool wrapper, but delegates into older ToolContext / ToolObservation code through safe_preview.

Problem:

```text
Two runtime conventions coexist:
  BaseTool / ToolRunContext / typed output
  ToolContext / ToolObservation / legacy handler
```

Consequence:

```text
1. inconsistent error shape
2. inconsistent trace shape
3. awkward validation bridge
4. harder testing
5. state semantics unclear
```

Recommended action:

```text
1. Port db.preview fully to BaseTool / ToolRunContext.
2. Remove ToolContext / ToolObservation bridge for model-facing tools.
3. Make all tools return typed plain outputs and let ToolRuntime wrap observations.
```

### 8.2 Tool Output Is Stored Too Broadly

Even when ToolMessage to the model is summarized, the full output can still be stored in state / last_tool_results / checkpoint.

Recommended action:

```text
1. Add model_summary and full_artifact separation.
2. Store large outputs as artifacts or server-side records.
3. Keep state small and deterministic.
4. Add output size caps per tool.
```

## 9. Semantic / Memory Residue Problems

### 9.1 Semantic Alias Remains in Core Code Paths

Current product direction removed semantic alias / metric / embedding from the main path.

But code still contains:

```text
semantic_aliases table
SemanticAliasResolver
db.remember writing SemanticAlias
memory/database_map semantic_index references
```

Problem:

```text
These features create conceptual noise and can leak into Agent behavior.
```

Recommended action:

```text
1. Do not expose semantic alias tools in the default Agent flow.
2. Do not write SemanticAlias from db.remember by default.
3. Keep DB columns/tables for compatibility only until migration cleanup.
4. Remove semantic references from prompt/tool descriptions unless actually supported.
```

### 9.2 db.remember Confirmation Is Not Integrated With Approval

db.remember can return status=pending_confirmation.

Problem:

```text
This is not the same as Agent approval interrupt.
```

Recommended action:

```text
Any write or memory operation requiring confirmation must go through PolicyGate + approval_node, not an ad-hoc output status.
```

### 9.3 Memory Write/Delete Should Not Be Default Agent Tools

memory.write and memory.delete are write operations.

Problem:

```text
They are registered and visible unless filtered, but policy blocks write side effects.
```

Recommended action:

```text
Hide memory.write/delete by default.
Expose only memory.search if explicitly needed.
Add user-triggered memory management UI later if product requires it.
```

## 10. SQL Safety / Execution Boundary Problems

### 10.1 db.query Combines Too Much

db.query combines:

```text
SQL safety validation
manual confirmation decision
execution
history writing
result serialization
```

Problem:

```text
Manual confirmation has no clean insertion point and becomes failed execution.
```

Recommended action:

```text
Replace model-facing db.query with:
  sql.validate
  sql.execute_readonly
```

This is covered in detail in:

```text
docs/designs/2026-06-20-agent-tool-approval-and-loop-control.md
```

### 10.2 Query History Writes Are Hidden Side Effects

execute_query writes QueryHistory as an audit side effect.

This is acceptable, but should be explicit in tool contract.

Recommended action:

```text
Document that sql.execute_readonly writes query history.
Ensure failures also write useful history without polluting main transaction.
```

## 11. Error Handling and Telemetry Problems

### 11.1 Too Many Broad Exception Handlers

Several paths catch broad exceptions and continue or log warnings.

Examples of risky patterns:

```text
FTS failure -> fallback silently
database_map build failure -> warning and continue
AI enrich batch failure -> rollback and continue
```

Problem:

```text
User sees degraded behavior; developer lacks enough signal to diagnose why.
```

Recommended action:

```text
1. Return degraded_mode metadata in tool outputs.
2. Emit structured telemetry for fallback paths.
3. Store last failure reason in datasource / enrichment status where relevant.
4. Avoid silently swallowing errors that affect core product behavior.
```

### 11.2 Failure Types Are Not Structured Enough

Tool failures often become strings.

Recommended action:

```text
Use structured error payloads:
  error_code
  error_type
  user_message
  debug_message
  retryable
  suggested_next_action
```

This helps progress logic avoid repeating the same failing tool.

## 12. Test Quality Problems

### 12.1 Tests Do Not Match Real Main Paths

Current tests often exercise idealized or fake tools instead of the actual registered Agent tools.

Problem examples:

```text
Policy tests cover fake sql.execute_readonly, while real Agent uses db.query.
AI enrich tests can monkeypatch behavior but do not cover real timeout/partial failure/search-doc staleness.
Semantic metric/alias tests cover APIs or resolver fragments, not real Agent chain.
```

Recommended action:

```text
Write tests against the actual registered tool registry and public API flows.
```

### 12.2 Missing Failure-Mode Tests

Required tests:

```text
schema sync without AI key succeeds
schema sync builds base schema_search_docs
AI enrich failure does not remove base docs
manual metadata edit rebuilds docs
db.search FTS failure falls back to docs search
db.search empty repeated does not loop
observe on 1000 fake tables returns capped output
schema.list_tables_page paginates
manual confirmation enters approval state, not query failure
preview uses unified runtime
```

### 12.3 Missing Large Catalog Tests

Add synthetic catalog tests:

```text
100 tables
1000 tables
5000 tables
wide table with 300 columns
many FK relationships
```

Assert:

```text
1. tool output size is capped
2. prompt summary size is capped
3. state/checkpoint size is bounded
4. calls complete within expected time
```

## 13. Frontend Flow Problems

### 13.1 Datasource Creation Triggers Too Much Work

If creating a datasource immediately syncs schema and possibly triggers AI enrich, the UI can feel stuck.

Recommended frontend flow:

```text
1. Create datasource
2. Test connection
3. Sync schema explicitly or automatically but only schema sync
4. Show sync result quickly
5. Offer AI enrich as separate action
```

### 13.2 No Clear Timeout / Cancellation Strategy

Long-running operations need cancellation or job-based progress.

Affected operations:

```text
schema sync on large datasource
AI enrich
schema refresh catalog
large preview/query
```

Recommended action:

```text
1. Add frontend AbortController / request timeout for normal calls.
2. Move long operations to job model.
3. Show progress and partial failure details.
```

### 13.3 UI Should Reflect Product Scope

Since metric rules, aliases, and embedding recall are removed from current scope, frontend should emphasize:

```text
datasource connection
schema sync
schema browser
table/column description editing
AI enrich descriptions
schema search
safe SQL answer loop
```

And hide:

```text
semantic alias management
embedding sync
metric rule management
memory write flows
```

## 14. Recommended Minimum Reliable Product Loop

The minimum product loop should be:

```text
1. User connects datasource.
2. System tests connection.
3. User syncs schema.
4. System writes schema_tables/schema_columns.
5. System builds base schema_search_docs.
6. User optionally runs AI enrich.
7. AI enrich updates descriptions and rebuilds docs.
8. User asks a natural-language question.
9. System searches schema_search_docs.
10. System inspects only relevant tables.
11. LLM generates SQL.
12. sql.validate checks safety.
13. sql.execute_readonly executes after approval if needed.
14. System returns result and SQL.
```

Everything outside this loop should be hidden or disabled until the loop is stable.

## 15. Recommended Cleanup Phases

### Phase 1 — Minimum Loop Stabilization

```text
1. Disable default AI enrich during schema sync.
2. Build base schema_search_docs after every schema sync.
3. Rebuild docs after manual metadata updates.
4. Add db.search fallback against schema_search_docs.
5. Cap db.observe and paginate list_tables.
6. Hide semantic/memory write tools from Agent.
```

### Phase 2 — Approval and Execution Boundary

```text
1. Add sql.validate.
2. Add sql.execute_readonly.
3. Remove db.query from model-facing tools.
4. Route manual confirmation to approval_node.
5. Add approval resume tests.
```

### Phase 3 — Runtime Normalization

```text
1. Port db.preview to the new BaseTool runtime.
2. Remove old ToolContext / ToolObservation bridge.
3. Add output-size classes to all tools.
4. Keep large outputs as artifacts, not state.
```

### Phase 4 — Catalog Scale Readiness

```text
1. Paginate all catalog list APIs.
2. Add large catalog synthetic tests.
3. Make DatabaseMap server-side only or remove from current loop.
4. Add schema_evidence state for Agent progress.
```

### Phase 5 — Product Scope Cleanup

```text
1. Keep semantic tables only for migration compatibility.
2. Remove semantic/embedding docs and frontend entry points.
3. Remove semantic/memory wording from default prompt/tool descriptions.
4. Keep only schema_search_docs + AI descriptions as the semantic layer for now.
```

## 16. Resume-Friendly Framing

This codebase can still be presented strongly if framed honestly:

```text
Built an AI-native database analysis workspace with datasource connection, schema catalog sync, AI table/column metadata enrichment, schema search retrieval, LLM-generated SQL validation, and safe read-only execution.

During development, identified and redesigned reliability issues around schema sync duplication, AI enrichment coupling, stale search indexes, large catalog context growth, recursive Agent tool calls, and manual approval boundaries.
```

This is a stronger and more truthful story than claiming the whole Agent system is production-perfect.

## 17. Final Recommendation

Stop adding features until this minimum loop is stable:

```text
schema sync
schema_search_docs
AI description enrich
schema search
SQL validate / execute
bounded tool output
approval flow
```

The rest should be deferred.
