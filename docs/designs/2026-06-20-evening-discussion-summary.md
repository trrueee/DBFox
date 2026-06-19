# Evening Discussion Summary: Schema Search Docs, Search Boundaries, and Tool Scope

> 2026-06-20 | summary of product/architecture decisions from the evening discussion

## 1. Core Conclusion

Tonight's discussion converged on a simpler and more practical direction:

```text
Do not try to make the Agent understand the entire database catalog in context.
Instead, make schema_search_docs good enough that the Agent can retrieve relevant tables/columns by search.
```

The main product loop should be:

```text
user question
  -> model generates a few search queries
  -> db.search searches schema_search_docs / schema_search_fts
  -> return top-N candidate tables and columns
  -> schema.describe_table confirms only a few candidates
  -> SQL validation and safe execution
```

This means large databases should be handled as searchable catalog indexes, not as full prompt context.

## 2. What We Should Do Well

### 2.1 Make `schema_search_docs` a Strong Internal Index

The most important work is to improve the quality of the `schema_search_docs` table.

It should not be a thin table-name index.

It should contain searchable language for both table-level and column-level retrieval.

Good docs should include:

```text
schema name
table name
column name
column type
table comment
column comment
AI table description
AI column description
business terms
semantic tags
aliases if present as metadata
subject area
grain
column role
metric type
important column names
important column descriptions
primary key summary
foreign key summary
relationship summary
Chinese and English terms where possible
```

This is what allows a user question like:

```text
订单退款金额
```

to retrieve candidates such as:

```text
order_refund_items.refund_amount
payments.refunded_amount
after_sale_orders.refund_fee
```

without showing the model thousands of table names.

### 2.2 Build Docs After Schema Sync, Not Only After AI Enrichment

`schema_search_docs` must exist after schema sync.

Correct flow:

```text
schema sync
  -> build base schema_search_docs from raw schema names/comments/types/FKs
  -> refresh schema_search_fts
  -> db.search is usable immediately

AI enrichment
  -> update schema_tables / schema_columns AI fields
  -> rebuild affected docs
  -> db.search becomes more accurate
```

Wrong flow:

```text
schema sync
  -> no docs
AI enrichment succeeds
  -> docs appear
AI enrichment fails or no API key
  -> db.search does not work
```

AI enrichment should improve retrieval quality, but it must not be a hard dependency for having docs.

### 2.3 Use Keyword / FTS Retrieval as MVP

Keyword-first retrieval is enough for the MVP.

This does not mean naive `LIKE` over table names only.

It means:

```text
model-generated queries
  -> schema_search_docs / FTS
  -> search across names, comments, AI descriptions, business terms, tags, aliases, roles
  -> top-N candidate table/column results
```

This is preferred for now because it is:

```text
explainable
debuggable
cheap
local-first
compatible with SQLite FTS
sufficient for many schema retrieval cases
```

Embedding recall is not required for the MVP.

### 2.4 Search Should Support Multiple Queries in One Call

This was an important concrete decision.

The model can generate a few different search queries for the same user question.

Example:

```json
{
  "queries": [
    "订单退款金额",
    "refund amount",
    "after_sale return payment"
  ],
  "limit": 10
}
```

MVP rule:

```text
db.search should accept at most 3 queries per call.
```

Recommended limits:

```text
max queries per call: 3
default returned candidates: 10
max model-facing candidates: 20
```

The tool should:

```text
1. search each query
2. merge results
3. dedupe by datasource/schema/table/column/entity_type
4. keep matched_query
5. keep matched_on
6. produce a short reason
7. return compact top-N candidates only
```

Good result shape:

```json
{
  "searched_terms": [
    "订单退款金额",
    "refund amount",
    "after_sale return payment"
  ],
  "results": [
    {
      "table": "order_refund_items",
      "column": "refund_amount",
      "entity_type": "column",
      "score": 18.4,
      "matched_query": "refund amount",
      "matched_on": ["column_name", "ai_description", "business_terms"],
      "reason": "Matched refund amount as a currency metric on order refund items."
    }
  ],
  "empty_queries": [
    "订单退款金额"
  ]
}
```

This avoids repeated tool calls such as:

```text
db.search("退款")
db.search("refund")
db.search("after_sale")
```

and reduces the chance of recursive search loops.

### 2.5 Search Must Have Boundaries

The model may generate keywords, translations, and related terms.

That is good.

But the system must enforce boundaries.

Rules:

```text
1. At most 3 queries in one db.search call.
2. Return 10 candidates by default.
3. Never return more than 20 model-facing candidates in MVP.
4. Do not allow infinite repeated search.
5. Duplicate queries in the same run should be ignored or rejected.
6. Search output must be compact.
7. Search output should include reason fields so the Agent can decide what to describe next.
```

The principle is:

```text
model chooses search terms;
system controls search budget.
```

## 3. What We Should Not Do Now

Tonight's direction is intentionally scoped down.

Do not build the following in the MVP:

```text
1. manual schema_search_docs editor
2. docs CRUD UI
3. docs approval workflow
4. docs versioning
5. docs management console
6. user-authored docs knowledge base
7. embedding recall as the primary search path
8. semantic metric rule recall
9. semantic alias as a primary product feature
10. complex docs lifecycle management
11. complex database exploration planner
12. full candidate-pool framework as the first step
13. broad tool deletion/addition discussion right now
```

The product goal is not documentation management.

The product goal is:

```text
reliable schema retrieval for AI database questioning.
```

So `schema_search_docs` should be:

```text
internal
derived
rebuildable
system-owned
not directly user-managed
```

If users need to improve retrieval quality, they should improve source metadata instead:

```text
table comments
column comments
table descriptions if already supported
column descriptions if already supported
AI enrichment inputs
```

Then DBFox regenerates the docs index.

## 4. Large Catalog Principle

Once `schema_search_docs` is good enough, the Agent should not receive thousands of tables as context.

Do not do:

```text
load all schema tables
load all columns
load full database map
send thousands of table names to the model
```

Do this instead:

```text
model generates up to 3 queries
  -> db.search searches docs/FTS
  -> returns top 10-20 candidates
  -> schema.describe_table expands only the top few
```

This is the core scalability strategy.

The database catalog is not prompt context.

The database catalog is a search space.

## 5. Tool-Layer Decision From Tonight

### 5.1 Simplify `db.observe`

`db.observe` should be simplified.

It should not be used as a full catalog dumping tool.

Future role:

```text
lightweight datasource/catalog overview
```

It should answer:

```text
Is the datasource connected?
Is catalog ready?
How many tables exist?
Is this a large catalog?
What are the top-level schemas/domains?
What should the Agent do next?
```

It should not return:

```text
all tables
all columns
all connected tables
full domain table lists
full database map
large nested schema payloads
```

Recommended output:

```json
{
  "catalog_status": "ready",
  "table_count": 3821,
  "large_catalog": true,
  "schemas": [
    {"name": "ods", "table_count": 1200},
    {"name": "dwd", "table_count": 900}
  ],
  "domains": [
    {"name": "order", "table_count": 320, "sample_tables": ["orders", "order_items"]}
  ],
  "next_action_hint": "Use db.search against schema_search_docs."
}
```

This keeps observe useful while preventing it from exploding context.

### 5.2 Do Not Discuss Other Tool Deletion/Additions Right Now

Earlier we discussed possible future tools such as:

```text
schema.list_tables_page
schema.expand_related_tables
candidate pool
enough/not-enough planner
```

Tonight's final scope is more conservative:

```text
Do not focus on adding or removing many tools right now.
```

The immediate tool-layer focus is:

```text
1. make db.search better
2. make db.search accept multiple queries with limits
3. make db.search return compact explainable candidates
4. simplify db.observe
5. keep other tool discussions for later
```

Existing tools such as `schema.describe_table`, `db.inspect`, `db.preview`, and SQL execution can remain in their current broader discussion bucket for now.

The key immediate change is not a new tool explosion.

The key immediate change is:

```text
strong docs index + bounded search + lightweight observe
```

## 6. Recommended MVP Flow

The practical MVP flow should be:

```text
1. User asks a database question.
2. Agent/model generates up to 3 search queries.
3. db.search searches schema_search_docs / schema_search_fts.
4. db.search returns top 10 candidates by default, max 20.
5. Agent chooses a few candidate tables/columns from the results.
6. Agent uses schema.describe_table for the top candidates.
7. Agent generates SQL from confirmed schema.
8. SQL is validated.
9. Safe read-only execution happens if allowed.
```

If search returns nothing:

```text
1. Do not dump all tables.
2. Do not repeatedly call the same search.
3. Use limited fallback inside db.search over schema_search_docs fields.
4. If still empty, ask clarification or check lightweight observe for catalog readiness.
```

## 7. Search Result Requirements

`db.search` should return results that are useful for both Agent reasoning and user trust.

Each result should include:

```text
entity_type
table
column if entity_type is column
score
matched_query
matched_on
reason
small excerpt or summary
```

Example:

```json
{
  "entity_type": "column",
  "table": "order_refund_items",
  "column": "refund_amount",
  "score": 18.4,
  "matched_query": "refund amount",
  "matched_on": ["column_name", "business_terms", "ai_description"],
  "reason": "Matched refund amount as a currency metric on order refund items."
}
```

This avoids opaque search results like:

```json
{"table": "order_refund_items", "score": 12.3}
```

## 8. Fallback Search Requirement

FTS is useful, but `schema_search_docs` is the fact source.

Search behavior should be:

```text
1. Try schema_search_fts.
2. If FTS fails or returns nothing, fallback to schema_search_docs keyword search.
3. Fallback must search docs fields, not only raw table/column names.
```

Fallback should search:

```text
search_text
ai_description
business_terms
semantic_tags
aliases
table_name
column_name
comments
```

This matters because if FTS is broken or too strict, recall should not collapse to weak name-only matching.

## 9. Tonight's Final Scope

### Do Now

```text
1. Make schema_search_docs high quality.
2. Ensure base docs exist after schema sync.
3. Make AI enrichment improve docs but not gate docs creation.
4. Make db.search support up to 3 queries in one call.
5. Make db.search return top 10 by default and max 20 model-facing candidates.
6. Merge and dedupe multi-query results.
7. Return matched_query, matched_on, and reason.
8. Add strong fallback search over schema_search_docs fields.
9. Simplify db.observe to lightweight catalog overview.
10. Avoid full catalog context injection.
```

### Do Not Do Now

```text
1. Do not build docs management UI.
2. Do not build manual docs editing workflow.
3. Do not make users manage schema_search_docs.
4. Do not build embedding recall as MVP.
5. Do not build semantic metric recall as MVP.
6. Do not expand the tool system discussion right now.
7. Do not add complex exploration tools before search docs quality is proven.
8. Do not make observe a full catalog dump.
9. Do not send thousands of tables to the model.
```

## 10. Why This Direction Is Good

This direction is good because it solves the main bottleneck with the smallest reliable change.

Instead of building a large Agent planner now, we improve the retrieval layer.

If retrieval is strong, the Agent needs fewer tools and less context.

The result is simpler:

```text
good docs index
  -> bounded multi-query search
  -> compact top-N candidates
  -> describe few tables
  -> safe SQL
```

This is easier to implement, easier to test, easier to explain, and easier to put on a resume.

Resume-friendly framing:

```text
Designed a keyword-first schema retrieval layer for an AI database agent, using system-generated schema_search_docs, AI-enriched metadata, bounded multi-query search, explainable candidate ranking, and lightweight catalog observation to avoid large-catalog context overflow.
```
