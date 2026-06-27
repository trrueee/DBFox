# Corrected Methodology Smoke Verification

Date: 2026-06-27

This is a smoke/directional run, not final decision support. It verifies benchmark wiring, corpus preparation, query policy behavior, and metric accounting before expanding sample size.

## Run Scope

- Cases: 6
- DBs: 3 (`concert_singer`, `pets_1`, `car_1`)
- Sampling: `round_robin_db`
- Query modes: `single`, `multi`
- Variants: 8 main variants, no diagnostic/stress variants
- Case rows: 96

## Acceptance Check

| Check | Result |
|---|---|
| raw/enriched docs coexist | pass |
| raw/enriched embeddings coexist | pass |
| raw docs have no AI metadata | pass |
| enriched docs have AI metadata | pass |
| docs equal embeddings for all 6 corpora | pass |
| query_policy present in case rows and summaries | pass |
| `hybrid_keyword_enriched_vector_raw_question` keyword datasource is enriched | pass |
| `hybrid_keyword_enriched_vector_raw_question` vector datasource is raw | pass |
| vector expression count is 1 | pass |
| `expression_embedding_call_count` is 0 | pass |
| vector recall excludes query embedding | pass |

## Corpus Prep

| DB | Profile | Docs | AI docs | Embeddings | Docs = embeddings |
|---|---|---:|---:|---:|---|
| `concert_singer` | raw | 25 | 0 | 25 | true |
| `pets_1` | raw | 17 | 0 | 17 | true |
| `car_1` | raw | 29 | 0 | 29 | true |
| `concert_singer` | enriched | 25 | 25 | 25 | true |
| `pets_1` | enriched | 17 | 17 | 17 | true |
| `car_1` | enriched | 29 | 29 | 29 | true |

## Key Mixed Hybrid Evidence

For `hybrid_keyword_enriched_vector_raw_question` in `multi` mode:

- `query_policy`: `multi_keyword_vector_question`
- `keyword_corpus_profile`: `enriched`
- `vector_corpus_profile`: `raw`
- `planner_expression_count`: 4
- `vector_expression_count`: 1
- `question_embedding_call_count`: 1
- `expression_embedding_call_count`: 0
- `db_search_call_count`: 5

Sample query split:

- keyword expressions: `["singer", "count singer", "singers", "singer count"]`
- vector expressions: `["How many singers do we have?"]`

Progress events also show enriched keyword datasource and raw vector datasource for this variant:

- keyword datasource: `spider_concert_singer_enriched_2f11e23e`
- vector datasource: `spider_concert_singer_raw_14b3589c`

## Timing Interpretation

The corrected main hybrid policy embeds the original question once for the vector leg. Planner expressions are used for keyword search only.

For `hybrid_keyword_enriched_vector_raw_question` / `multi`:

- avg planner expressions: 4.0
- avg question embedding calls: 1.0
- avg expression embedding calls: 0.0
- p95 query embedding: 448.381 ms
- p95 vector recall: 11.535 ms
- p95 measured provider: 1552.728 ms
- p95 modeled online: 1567.385 ms

This confirms `vector_recall_ms` is not hiding query embedding time.

## Next Step

Proceed to 24 cases / 3 DBs with the same corrected main policies plus opt-in diagnostic/stress `expression_each` variants. The diagnostic rows must remain outside the main recommendation table.
