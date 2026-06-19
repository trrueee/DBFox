# Schema Search Docs Index MVP

> 2026-06-20 | design note for keyword-first schema retrieval

## 1. Purpose

This document defines the MVP design for `schema_search_docs` as DBFox's primary schema retrieval index.

The goal is to make database exploration work through a high-quality internal schema search index, not through full catalog prompts, embeddings, or manual document management.

The core idea is:

```text
schema catalog + comments + AI enrichment
  -> derived schema_search_docs
  -> FTS / keyword retrieval
  -> top-N candidate tables and columns
  -> describe / inspect only a few candidates
```

This document also explicitly records a product decision:

```text
Do not build manual editing, management, versioning, or admin workflows for schema_search_docs in the MVP.
```

`schema_search_docs` should be an internal derived index, not a user-managed knowledge base.

## 2. Decision Summary

### Keep

```text
1. schema_search_docs as an internal derived table.
2. schema_search_fts as the searchable FTS index over docs.
3. table-level docs.
4. column-level docs.
5. keyword / FTS retrieval as the MVP recall layer.
6. model-generated multi-query search terms.
7. AI enrichment as an index quality improvement.
8. explainable search results with matched_query, matched_on, and reason.
```

### Do Not Build in MVP

```text
1. manual schema_search_docs editor
2. docs CRUD UI
3. docs approval workflow
4. docs version management
5. docs review queue
6. docs admin console
7. per-doc lifecycle management
8. user-authored docs as a separate knowledge base
9. embedding recall as the primary search layer
10. semantic metric rule recall as the primary search layer
```

The MVP should not require users to understand or manage `schema_search_docs` directly.

Users may still edit table or column descriptions if that already exists as metadata, but `schema_search_docs` itself remains system-generated.

## 3. Why Docs Index Quality Is the Priority

The Agent's exploration quality depends on whether schema terms can be retrieved from the catalog.

If the docs index is weak, the Agent will compensate by:

```text
repeating search
calling observe
listing too many tables
inspecting random tables
asking unnecessary clarification
or failing after max steps
```

If the docs index is strong, the Agent can:

```text
search a few model-generated terms
get top candidate tables/columns
inspect only those candidates
avoid large catalog context overflow
```

Therefore, the priority is not a smarter Agent first.

The priority is:

```text
make schema_search_docs contain the right searchable language.
```

## 4. MVP Retrieval Strategy

The MVP should use keyword-first retrieval.

This means:

```text
user question
  -> model generates a few search terms
  -> search schema_search_docs / schema_search_fts
  -> merge and dedupe top results
  -> return candidate tables and columns with reasons
```

Example user question:

```text
订单退款金额
```

Possible model-generated queries:

```text
订单退款金额
refund amount
after_sale return payment
```

The system should search all of them, merge results, and return compact candidates.

This is enough for the MVP because schema search is mostly a named-object retrieval problem:

```text
table names
column names
comments
AI descriptions
business terms
semantic tags
aliases as metadata if available
```

The search layer does not need to solve every semantic ambiguity. It only needs to produce good candidates for `schema.describe_table` or `db.inspect`.

## 5. What schema_search_docs Should Represent

`schema_search_docs` should contain one row per searchable schema object.

At minimum:

```text
1. one table-level document per table
2. one column-level document per searchable column
```

### 5.1 Table-Level Document

A table-level doc should summarize what the table is about.

Recommended fields used in search text:

```text
schema name
table name
table comment
AI table description
business terms
semantic tags
aliases if available as metadata
subject area
grain
important column names
important column descriptions
primary key summary
foreign key summary
relationship summary
```

Example:

```json
{
  "entity_type": "table",
  "table_name": "order_refund_items",
  "name": "order_refund_items",
  "ai_description": "Stores refund item records for customer orders.",
  "business_terms": ["refund", "return", "after_sale", "退款", "售后"],
  "semantic_tags": ["order", "payment", "refund"],
  "grain": "one row per refunded order item",
  "subject_area": "order",
  "search_text": "order_refund_items refund return after_sale 退款 售后 refund item order payment ..."
}
```

### 5.2 Column-Level Document

A column-level doc should make fields directly retrievable.

Recommended fields used in search text:

```text
schema name
table name
column name
column type
column comment
AI column description
business terms
semantic tags
aliases if available as metadata
column role
metric type
table description
table business terms
```

Example:

```json
{
  "entity_type": "column",
  "table_name": "order_refund_items",
  "column_name": "refund_amount",
  "name": "order_refund_items.refund_amount",
  "ai_description": "Amount refunded to the customer.",
  "business_terms": ["refund amount", "refunded money", "退款金额"],
  "column_role": "metric",
  "metric_type": "currency",
  "search_text": "order_refund_items refund_amount refund amount refunded money 退款金额 currency ..."
}
```

Column docs should include a small amount of table-level context so that isolated column names are not too ambiguous.

## 6. Search Text Construction

`search_text` is the most important field.

It should not be just:

```text
table_name column_name
```

It should be a carefully composed retrieval document.

### 6.1 Table Search Text

Recommended composition:

```text
{schema}.{table}
{table_comment}
{ai_description}
{business_terms}
{semantic_tags}
{aliases}
{subject_area}
{grain}
{primary_key_summary}
{foreign_key_summary}
{important_column_names}
{important_column_descriptions}
```

### 6.2 Column Search Text

Recommended composition:

```text
{schema}.{table}.{column}
{column_type}
{column_comment}
{ai_description}
{business_terms}
{semantic_tags}
{aliases}
{column_role}
{metric_type}
{table_ai_description}
{table_business_terms}
```

### 6.3 Multilingual Terms

The index should allow both Chinese and English terms to work.

For example, a refund field should be searchable by:

```text
退款
退款金额
售后
退货
refund
refund amount
return
after_sale
reimbursement
payment reversal
```

This can come from:

```text
raw comments
AI enrichment
business_terms
semantic_tags
model-generated search queries
```

No separate docs management UI is required for this MVP.

## 7. AI Enrichment Role

AI enrichment should improve docs quality, but docs must not depend on AI enrichment to exist.

Correct flow:

```text
schema sync
  -> build base schema_search_docs from raw schema names/comments
  -> build or refresh FTS
  -> db.search is usable immediately

AI enrich
  -> update schema_tables / schema_columns AI fields
  -> rebuild affected schema_search_docs
  -> db.search becomes more accurate
```

Wrong flow:

```text
schema sync
  -> no docs
AI enrich succeeds
  -> docs appear
AI enrich fails or no API key
  -> search does not work
```

MVP requirement:

```text
schema_search_docs must be available after schema sync, even without LLM enrichment.
```

AI enrichment is an enhancement layer, not a hard dependency.

## 8. No Manual Docs Management in MVP

This is an explicit product decision.

Do not build a separate UX where users edit or manage `schema_search_docs` directly.

Do not build:

```text
docs editor
docs list page
docs admin page
docs approval workflow
docs version history
docs publishing workflow
docs ownership model
docs conflict resolution
docs lifecycle state machine
```

Reason:

```text
The product goal is reliable schema retrieval, not a documentation management system.
```

For now, `schema_search_docs` should be treated as:

```text
internal, derived, rebuildable, system-owned search index
```

If users need to improve search quality, they should improve source metadata instead:

```text
table comments
column comments
table descriptions if already supported
column descriptions if already supported
AI enrichment inputs
```

The search docs should then be regenerated from those source fields.

## 9. FTS and Fallback Behavior

`schema_search_fts` should be treated as an acceleration/search structure over `schema_search_docs`.

The fact source is:

```text
schema_search_docs
```

The search index is:

```text
schema_search_fts
```

Search should behave like:

```text
1. try FTS search
2. if FTS errors or returns nothing, fallback to schema_search_docs keyword search
3. fallback must search docs fields, not only raw schema table/column names
```

Fallback should include:

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

This prevents FTS failure from reducing recall to weak table-name-only matching.

## 10. Multi-Query Search

The model should be allowed to generate a few search terms.

But the system should enforce search budget and dedupe.

Recommended input shape:

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

Recommended output shape:

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

Rules:

```text
1. max 3 queries per search call in MVP
2. dedupe by datasource/schema/table/column/entity_type
3. keep matched_query for explanation
4. merge scores across queries
5. return compact top-N results only
```

This avoids repeated tool calls like:

```text
db.search("退款")
db.search("refund")
db.search("after_sale")
```

and reduces Agent loop risk.

## 11. Search Result Explanation

Search results must be explainable.

Bad result:

```json
{"table": "order_refund_items", "score": 12.3}
```

Good result:

```json
{
  "table": "order_refund_items",
  "column": "refund_amount",
  "score": 18.4,
  "matched_query": "refund amount",
  "matched_on": ["column_name", "business_terms", "ai_description"],
  "reason": "Matched refund amount as a currency metric on order refund items."
}
```

Reasons help:

```text
1. the Agent choose between candidates
2. the user trust the selected table
3. debugging poor recall
4. tests assert retrieval behavior
```

## 12. Current vs MVP Target

| Area | Current / risk | MVP target |
|---|---|---|
| Docs ownership | Docs are currently implementation detail, but not formalized | Docs are internal derived index |
| Docs creation | Tied too strongly to enrichment path in practice | Base docs built after schema sync |
| AI enrich | Improves table/column metadata | Improves docs quality, not required for docs existence |
| Manual docs management | Not needed | Explicitly out of scope |
| Search | FTS first, fallback may be weak | FTS plus docs-field fallback |
| Query generation | Model can generate terms | Model generates up to 3 queries, system dedupes and merges |
| Result explanation | Limited | matched_query, matched_on, reason |
| Large catalog behavior | Search quality determines whether Agent falls back to heavy tools | Strong docs index reduces observe/list pressure |

## 13. Minimal Implementation Plan

### Phase 1 — Stable Base Docs

```text
1. Ensure schema sync always builds base schema_search_docs.
2. Build both table docs and column docs.
3. Build search_text from raw schema name/comment/type/FK metadata.
4. Refresh schema_search_fts after docs change.
5. Ensure db.search works without AI enrichment.
```

### Phase 2 — Better AI-Enhanced Docs

```text
1. After AI enrich finishes for a table, rebuild docs for that table.
2. Include ai_description, business_terms, semantic_tags, aliases as metadata if present.
3. Include table context in column docs.
4. Do not expose docs as editable objects.
```

### Phase 3 — Search API Improvements

```text
1. Let db.search accept queries: list[str].
2. Limit to max 3 queries in MVP.
3. Merge and dedupe results.
4. Return matched_query, matched_on, and reason.
5. Strengthen fallback to search schema_search_docs fields.
```

### Phase 4 — Tests

```text
1. schema sync without API key still creates docs.
2. table name search works.
3. column name search works.
4. table comment search works.
5. column comment search works.
6. AI description search works after enrichment.
7. business_terms search works after enrichment.
8. Chinese query can match English-enriched docs.
9. multi-query search dedupes results.
10. FTS failure falls back to schema_search_docs.
```

## 14. Out of Scope

Explicitly out of scope for this MVP:

```text
1. embedding recall
2. vector database
3. user-managed docs
4. docs UI
5. docs approval workflow
6. docs versioning
7. metric formula recall
8. semantic alias as a primary product feature
9. auto memory writes into docs
10. full knowledge-base management
```

These can be reconsidered later, but they are not required for the first reliable database exploration loop.

## 15. Final Recommendation

Make `schema_search_docs` a reliable internal derived index.

Do not make it a user-facing documentation management product in the MVP.

The minimum reliable retrieval loop should be:

```text
schema sync builds base docs
AI enrich improves docs
model generates up to 3 search queries
schema_search_docs / FTS retrieves top candidates
search returns matched_query / matched_on / reason
Agent describes only top candidate tables
SQL is generated from confirmed schema
```

This keeps the product focused:

```text
not docs management
not embedding research
not semantic metric infrastructure

but reliable schema retrieval for database exploration
```

Resume-friendly summary:

```text
Designed a keyword-first schema retrieval index for an AI database agent, using system-generated schema_search_docs, FTS search, AI-enriched metadata, multi-query retrieval, and explainable candidate ranking while explicitly deferring manual docs management and embedding recall.
```
