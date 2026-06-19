# Large-Catalog-Safe Database Exploration Protocol

> 2026-06-20 | design proposal for controlled database exploration under context limits

## 1. Purpose

This document proposes a new tool and state design for DBFox Agent database exploration.

The goal is not to show the model the whole database.

The goal is:

```text
Given a vague user question and a large database catalog,
progressively discover relevant tables and columns,
expand the search range when candidates are insufficient,
confirm only a small number of likely tables,
and avoid overflowing the model context, Agent state, frontend events, or checkpoints.
```

This design is especially important for catalogs with hundreds or thousands of tables.

## 2. Is This Design Reasonable?

Yes. The design is reasonable because it matches how large database exploration must work under LLM context constraints.

A large catalog cannot be treated as prompt context. It must be treated as an indexed search space.

The Agent should not receive:

```text
all table names
all columns
all relationships
full database map
all schema/domain table lists
```

Instead, the Agent should receive only:

```text
small environment summary
retrieved top-N schema candidates
paginated table list slices
related-table expansion around known candidates
precise descriptions of a few candidate tables
small live previews only when needed
```

The design is also reasonable because it separates four different tasks that are currently mixed:

```text
1. environment awareness
2. candidate discovery
3. candidate expansion
4. exact table confirmation
```

Current DBFox tools have pieces of these abilities, but they are not organized into an exploration protocol.

## 3. Current Behavior Summary

Current registered tools include:

```text
environment.get_profile
db.observe
db.search
schema.list_tables
schema.describe_table
schema.refresh_catalog
db.inspect
db.preview
db.query
```

The current database workflow is closer to:

```text
observe / search / inspect / preview / query
```

But there is no hard system rule for:

```text
how many times search can be retried
how to broaden search terms
how to keep a candidate table pool
how to page through possible tables
how to expand from candidate relationships
how to decide enough vs not enough
how to avoid dumping full catalog into state
```

As a result, when `db.search` returns weak or empty results, the model may:

```text
repeat search
call observe and receive too much catalog information
list all tables
inspect arbitrary tables
run until max steps
```

## 4. Current vs Proposed Design

| Area | Current behavior | Proposed behavior |
|---|---|---|
| Database overview | `db.observe` returns broad schema/domain/table summaries | `db.observe` becomes lightweight datasource/catalog overview only |
| Table discovery | `db.search` exists but no controlled broaden strategy | `schema.search` / `db.search` becomes primary top-N candidate discovery over `schema_search_docs` |
| Search failure | Model may retry or switch tools freely | Search failure enters controlled expansion ladder |
| Table listing | `schema.list_tables` returns all tables | `schema.list_tables_page` returns paginated, filtered slices |
| Candidate state | No explicit candidate pool | Maintain `candidate_tables`, `searched_terms`, `described_tables`, and `missing_requirements` |
| Relationship expansion | `connected_tables` appears inside observe summaries | Dedicated `schema.expand_related_tables(table, depth, limit)` |
| Table confirmation | `schema.describe_table` exact match or failure | `schema.describe_table` supports suggestions, schema-qualified names, and structured not_found |
| Live structure | `db.inspect` can inspect one target | Keep `db.inspect` for live verification only after candidates exist |
| Context control | Large outputs can enter state/checkpoint | Every exploration tool has output budget and summary/full-artifact split |
| Loop control | Tool observation often counts as progress | Empty/repeated tools do not count as useful progress |

## 5. Key Design Principle: Search Space, Not Context

For thousands of tables, schema information must be handled as a search index, not as a prompt appendix.

The primary search substrate should be:

```text
schema_tables
schema_columns
schema_search_docs
schema_search_fts
```

`schema_search_docs` is the model-facing search document table.

It should contain searchable rows for:

```text
table-level documents
column-level documents
AI-enriched descriptions
business terms
semantic tags
aliases if retained as metadata
comments
raw table/column names
```

The Agent should query this index and receive only top-N results.

## 6. Proposed Tool Taxonomy

Tools should be organized by exploration ability, not only by namespace.

### 6.1 Environment Status Tools

#### `environment.get_profile`

Purpose:

```text
Return datasource environment, dialect, catalog status, table count, and warnings.
```

Should not return full database map.

#### `db.observe` / future `datasource.overview`

New role:

```text
Lightweight datasource and catalog health overview.
```

Allowed output:

```text
datasource_id
datasource_name
dialect
catalog_status
table_count
schema_count
domain_count
large_catalog
schema summaries
domain summaries
warnings
next_action_hint
```

Forbidden output:

```text
all tables
all columns
all connected_tables
full database map
full domain table lists
```

Recommended large catalog output:

```json
{
  "dialect": "mysql",
  "catalog_status": "ready",
  "table_count": 3821,
  "large_catalog": true,
  "schemas": [
    {"name": "ods", "table_count": 1200},
    {"name": "dwd", "table_count": 900}
  ],
  "domains": [
    {"name": "order", "table_count": 320, "sample_tables": ["orders", "order_items"]},
    {"name": "payment", "table_count": 180, "sample_tables": ["payments"]}
  ],
  "next_action_hint": "Use schema.search to find candidate tables."
}
```

### 6.2 Candidate Discovery Tools

#### `schema.search` / current `db.search`

Purpose:

```text
Find top-N relevant table/column candidates from schema_search_docs / FTS.
```

Input:

```json
{
  "query": "订单退款金额",
  "limit": 10,
  "entity_type": "both",
  "schema": null,
  "domain": null
}
```

Output:

```json
{
  "query": "订单退款金额",
  "results": [
    {
      "table": "order_refund_items",
      "column": "refund_amount",
      "entity_type": "column",
      "score": 18.4,
      "matched_on": ["column_name", "ai_description", "business_terms"],
      "reason": "matched refund amount semantics"
    }
  ],
  "has_results": true
}
```

Hard limits:

```text
limit default 10
limit max 20
no duplicate query in same run
max 2-3 distinct schema.search calls per run unless user gives new terms
```

### 6.3 Candidate Expansion Tools

#### `schema.list_tables_page`

Purpose:

```text
Expand candidate table pool when search results are weak or empty.
```

This is not a full catalog dump. It is a paginated, filtered directory lookup.

Input:

```json
{
  "query": "refund",
  "schema": "dwd",
  "domain": "order",
  "limit": 50,
  "cursor": null
}
```

Output:

```json
{
  "tables": [
    {
      "table": "dwd_order_refund",
      "schema": "dwd",
      "columns_count": 42,
      "row_count_estimate": 1230000,
      "reason": "table_name matched refund"
    }
  ],
  "has_more": true,
  "next_cursor": "..."
}
```

Hard limits:

```text
limit default 50
limit max 100
must support query/schema/domain filters
must never return all tables by default
```

#### `schema.expand_related_tables`

Purpose:

```text
Expand from known candidate tables through FK, reverse FK, or naming-based relationships.
```

Input:

```json
{
  "table": "order_refund_items",
  "depth": 1,
  "limit": 20
}
```

Output:

```json
{
  "base_table": "order_refund_items",
  "related_tables": [
    {
      "table": "orders",
      "relation": "order_refund_items.order_id -> orders.id",
      "source": "fk_catalog",
      "confidence": 1.0
    },
    {
      "table": "payments",
      "relation": "order_refund_items.payment_id -> payments.id",
      "source": "fk_catalog",
      "confidence": 1.0
    }
  ]
}
```

Hard limits:

```text
depth default 1
max depth 2
limit default 20
limit max 50
no full graph traversal
```

### 6.4 Exact Confirmation Tools

#### `schema.describe_table`

Purpose:

```text
Return catalog-backed table structure for a specific candidate table.
```

Should include:

```text
table name
schema
table type
row estimate
column names/types
primary keys
foreign keys
comments
AI descriptions if available
truncated flag for wide tables
```

Current issue:

```text
The current implementation uses exact table_name lookup and raises when not found.
```

Proposed behavior:

```text
1. support schema.table
2. support case-insensitive exact match
3. return structured not_found with similar_tables
4. do not throw plain exceptions for normal not-found exploration
```

#### `db.inspect`

Purpose:

```text
Live metadata verification for a specific table or column.
```

Use only after candidate table exists or when catalog is suspected stale.

Should not be used for broad exploration.

Hard limits:

```text
summary mode default
full mode explicit
column/index/FK caps for wide tables
```

### 6.5 Data Sampling Tool

#### `db.preview`

Purpose:

```text
Preview a small number of live rows to confirm value semantics.
```

Use when:

```text
field values are ambiguous
status/enums need interpretation
the user asks to see sample rows
```

Do not use as first-line table discovery.

Hard limits:

```text
default rows 5-10
max rows 20
column whitelist
cell truncation
redaction
prod restrictions
```

### 6.6 SQL Execution Tools

Future model-facing SQL tools should be:

```text
sql.validate
sql.execute_readonly
```

not `db.query` as one combined operation.

`sql.validate`:

```text
validate generated SQL
produce safe_sql and safety decision
do not execute
```

`sql.execute_readonly`:

```text
execute only validated safe_sql
consume safety decision
route manual confirmation through approval if needed
```

## 7. Proposed Candidate Pool State

A large-catalog exploration Agent needs explicit state.

Example:

```json
{
  "candidate_tables": [
    {
      "table": "order_refund_items",
      "source": "schema.search",
      "score": 18.4,
      "reason": "matched refund amount",
      "status": "candidate"
    },
    {
      "table": "payments",
      "source": "schema.expand_related_tables",
      "reason": "order_refund_items.payment_id -> payments.id",
      "status": "candidate"
    }
  ],
  "searched_terms": [
    "订单退款金额",
    "refund",
    "after_sale"
  ],
  "described_tables": [
    "order_refund_items"
  ],
  "missing_requirements": [
    "need payment table",
    "need time column"
  ],
  "exhausted_paths": [
    "schema.search:订单退款金额"
  ]
}
```

Why this is necessary:

```text
1. prevents repeated search
2. keeps candidates across steps
3. allows controlled expansion
4. allows enough/not-enough decisions
5. avoids relying on model memory alone
```

## 8. Enough / Not Enough Decision

Every exploration step should classify whether the current candidate pool is enough.

Enough:

```text
1. one to three plausible tables exist
2. required metric columns are found
3. required dimension/group columns are found
4. required time columns are found if the question is time-based
5. join path is known or explainable if multiple tables are needed
```

Not enough reasons:

```text
no_candidates
low_confidence
missing_metric_column
missing_time_column
missing_dimension_column
missing_join_table
catalog_empty
catalog_stale
ambiguous_business_term
```

Expansion strategy should depend on reason:

| Reason | Next action |
|---|---|
| no_candidates | broaden search, then list_tables_page |
| low_confidence | broaden search, list_tables_page by keyword/domain |
| missing_metric_column | search metric term, list columns/docs by metric term |
| missing_time_column | search date/time/created_at terms |
| missing_join_table | expand_related_tables |
| catalog_empty | lightweight observe, then refresh or ask user |
| catalog_stale | inspect known candidates or refresh catalog |
| ambiguous_business_term | ask user after limited exploration |

## 9. Exploration Ladder

### 9.1 Normal Question Flow

```text
user question
  -> environment.get_profile or lightweight observe
  -> schema.search(question)
  -> add top results to candidate_pool
  -> schema.describe_table(top 1-3 candidates)
  -> sql.validate
  -> sql.execute_readonly
```

### 9.2 Search Returns Nothing

```text
schema.search(exact question)
  -> empty
schema.search(broadened terms)
  -> empty or weak
schema.list_tables_page(query=broadened keyword)
  -> add candidates
schema.describe_table(top candidates)
```

### 9.3 Candidate Tables Are Insufficient

```text
schema.describe_table(candidate)
  -> missing join table or supporting dimension
schema.expand_related_tables(candidate, depth=1)
  -> add related candidates
schema.describe_table(top related candidates)
```

### 9.4 Still Insufficient

```text
lightweight observe
  -> check catalog_status, schemas, domains, large_catalog
  -> decide refresh_catalog or ask clarification
```

Important rule:

```text
observe is used to check status and direction, not to dump all tables.
```

## 10. Context Budget Rules

Every tool must have explicit output budgets.

| Tool | Model-facing budget |
|---|---|
| environment.get_profile | small, < 1KB ideal |
| db.observe | small, no full table list |
| schema.search | top 10-20, each result compact |
| schema.list_tables_page | default 50 tables, max 100 |
| schema.expand_related_tables | depth 1, limit 20 by default |
| schema.describe_table | cap wide tables, return truncated flag |
| db.inspect | summary mode by default |
| db.preview | 5-10 rows by default, max 20 |
| sql.execute_readonly | result rows summarized/artifacted |

Large outputs should be separated:

```text
model_summary:
  compact text/JSON for LLM reasoning

full_artifact:
  complete rows/details for frontend/debug/storage
```

The Agent state should store summaries and artifact IDs, not full large payloads by default.

## 11. Environment Restrictions

Tools should be classified by environment risk.

### Catalog-only tools

```text
environment.get_profile
db.observe
schema.search
schema.list_tables_page
schema.describe_table
schema.expand_related_tables
```

These should be safe by default because they use DBFox catalog/search docs, not live data.

### Live metadata tools

```text
db.inspect
```

Requires real datasource connection.

Should be limited in prod and large catalogs.

### Live data tools

```text
db.preview
sql.execute_readonly
```

These should be protected by row limits, redaction, TrustGate, and approval if needed.

### Expensive mutation / refresh tools

```text
schema.refresh_catalog
AI enrich
memory writes
```

These should not be auto-called during normal exploration.

## 12. Current Implementation Gaps

### 12.1 db.observe Is Too Heavy

Current behavior loads all catalog tables and builds schema/domain sections from all selected tables.

Gap:

```text
observe acts like full database map rather than lightweight overview.
```

Required change:

```text
Cap observe output and remove full table summaries for large catalogs.
```

### 12.2 schema.list_tables Is Not Paginated

Current behavior returns all known tables.

Gap:

```text
No query/schema/domain filter, no cursor, no limit.
```

Required change:

```text
Replace or supplement with schema.list_tables_page.
```

### 12.3 db.search Has No Exploration Policy

Current db.search can search FTS and fallback once, but the Agent has no controlled broaden strategy.

Gap:

```text
No searched_terms state, no duplicate search guard, no max attempts, no enough/not-enough reason.
```

Required change:

```text
Add search attempt tracking and candidate_pool updates.
```

### 12.4 describe_table Fails Instead of Suggesting

Current describe_table raises if exact table name is missing.

Gap:

```text
Not-found during exploration should produce structured suggestions, not generic failure.
```

Required change:

```text
Return not_found with similar_tables and possible schema-qualified matches.
```

### 12.5 No Relationship Expansion Tool

Current related table information may appear in observe or live inspect, but there is no controlled candidate expansion tool.

Gap:

```text
The Agent cannot explicitly ask: given this table, what related tables should I consider?
```

Required change:

```text
Add schema.expand_related_tables.
```

### 12.6 No Candidate Pool

Current Agent relies mostly on model conversation context and last_tool_results.

Gap:

```text
Candidates are not first-class state.
```

Required change:

```text
Add candidate_tables state and merge rules.
```

## 13. Why This Is Better Than the Current Design

### Better under context limits

Current design risks loading too much catalog into tool outputs.

Proposed design never requires all tables in context.

### Better for large databases

Current design works for dozens of tables but does not scale to thousands.

Proposed design uses indexed search, pagination, and local relationship expansion.

### Better for debugging

Current exploration failures look like generic search/observe loops.

Proposed design records:

```text
searched_terms
candidate sources
missing requirements
exhausted paths
not_enough reason
```

### Better for safety

Current design can jump from failed search to live inspect/preview/query unpredictably.

Proposed design uses catalog-only tools first, live tools only after candidates are narrowed.

### Better for product UX

Current behavior can feel random.

Proposed behavior can be shown to users as a clear exploration trace:

```text
Searched schema docs for refund.
Broadened to after_sale/payment.
Found 5 candidate tables.
Expanded related tables from refund_items.
Inspected 3 tables.
Generated SQL from confirmed schema.
```

## 14. Minimal Implementation Plan

### Phase 1 — Make Existing Tools Safe

```text
1. Change db.observe to lightweight overview.
2. Add output caps to db.observe.
3. Add duplicate db.search guard.
4. Add max search attempts per run.
5. Strengthen db.search fallback against schema_search_docs.
```

### Phase 2 — Add Expansion Tools

```text
1. Add schema.list_tables_page.
2. Add schema.expand_related_tables.
3. Add candidate_tables state.
4. Add searched_terms and exhausted_paths state.
```

### Phase 3 — Add Enough/Not-Enough Logic

```text
1. Add not_enough reason classification.
2. Route no_candidates to broaden/list.
3. Route missing_join_table to expand_related_tables.
4. Route catalog_empty to observe/refresh.
5. Stop exploration after bounded attempts and ask clarification.
```

### Phase 4 — Normalize SQL and Live Tools

```text
1. Use sql.validate + sql.execute_readonly.
2. Keep db.inspect and db.preview after candidate narrowing only.
3. Keep large outputs as artifacts, not state.
```

## 15. Tests Required

### Search and expansion tests

```text
exact search returns candidates
empty search broadens once
same query cannot repeat
search attempts stop after configured limit
list_tables_page returns filtered page only
expand_related_tables returns depth-1 FK neighbors
candidate_pool deduplicates tables by name/schema
```

### Large catalog tests

```text
1000 fake tables do not make observe exceed output budget
list_tables_page returns only first page
search returns top N only
candidate_pool remains bounded
checkpoint/state size remains bounded
```

### Not-enough routing tests

```text
no_candidates -> broaden/list
missing_join_table -> expand_related_tables
catalog_empty -> observe/refresh path
low_confidence -> broaden/list
```

### Safety tests

```text
catalog-only tools do not connect to live DB
inspect connects only for known candidate
preview/query are never called before candidate narrowing
prod datasource requires approval where appropriate
```

## 16. Resume-Friendly Summary

This design can be summarized as:

```text
Designed a large-catalog-safe database exploration protocol for an LLM Agent, using schema document retrieval, paginated catalog search, candidate table state, relationship expansion, and bounded tool outputs to progressively discover relevant schema without overflowing context.
```

This is a strong design point because it addresses a real problem in AI database agents:

```text
LLMs cannot reason over thousands of tables directly; they need controlled retrieval and expansion.
```

## 17. Final Recommendation

Adopt this exploration protocol.

Do not rely on `observe` or full catalog prompts for large databases.

The minimum viable exploration stack should be:

```text
lightweight observe / environment profile
schema.search over schema_search_docs
schema.list_tables_page
schema.expand_related_tables
schema.describe_table
optional db.inspect
optional db.preview
sql.validate
sql.execute_readonly
```

The core shift is:

```text
from: model sees database map and figures it out

to: model drives a bounded retrieval process over catalog/search indexes
```

That shift is necessary for large-catalog reliability.
