# Mixed Retrieval Profile Verification Report

Date: 2026-06-27

## Scope

This run verifies the expanded retrieval profile matrix with real Qwen-compatible planner/enrichment/embedding provider settings loaded from `C:\Users\Lenovo\.dbfox\dbfox-eval.env`. API keys are intentionally not written into this report or committed artifacts.

Dataset:
- Source: Spider `dev.json` from local `DBFOX_SPIDER_ROOT`
- Sampling: `round_robin_db`
- Cases: 24
- DBs: 3 (`concert_singer`, `pets_1`, `car_1`), 8 cases each
- Query modes: `single`, `multi`
- Matrix size: 8 variants x 2 query modes x 24 cases = 384 case rows

## Profile Matrix

The run covers the full matrix needed to separate keyword corpus text from vector embedding text:

| Variant | Keyword corpus | Vector corpus |
|---|---|---|
| `keyword_raw` | raw | none |
| `vector_raw` | none | raw |
| `keyword_enriched` | raw + AI fields | none |
| `vector_enriched` | none | raw + AI fields |
| `hybrid_raw` | raw | raw |
| `hybrid_keyword_enriched_vector_raw` | raw + AI fields | raw |
| `hybrid_keyword_raw_vector_enriched` | raw | raw + AI fields |
| `hybrid_enriched` | raw + AI fields | raw + AI fields |

The mixed hybrid path is verified by `progress_events.jsonl`: for `hybrid_keyword_enriched_vector_raw`, `datasource_id` points to enriched corpus while `vector_datasource_id` points to raw corpus; for `hybrid_keyword_raw_vector_enriched`, the reverse is true.

## Prep Check

Raw and enriched corpora both exist for each selected DB, and both have embeddings:

| DB | Profile | Docs | AI metadata docs | Embeddings | Docs = embeddings |
|---|---|---:|---:|---:|---|
| `concert_singer` | raw | 25 | 0 | 25 | true |
| `pets_1` | raw | 17 | 0 | 17 | true |
| `car_1` | raw | 29 | 0 | 29 | true |
| `concert_singer` | enriched | 25 | 25 | 25 | true |
| `pets_1` | enriched | 17 | 17 | 17 | true |
| `car_1` | enriched | 29 | 29 | 29 | true |

Planner warmup was recorded separately: `18024.613ms`, with `planner_warmup_in_case_latency=false`.

## Result Summary

Single-query highlights:
- `vector_enriched`: table@5 `100.00%`, column@10 `91.67%`, mrr_column `0.4410`.
- `vector_raw`: table@5 `91.67%`, column@10 `91.67%`, mrr_column `0.3819`.
- `hybrid_keyword_enriched_vector_raw`: table@5 `95.83%`, column@10 `87.50%`.
- `hybrid_raw`: table@5 `95.83%`, column@10 `87.50%`.
- `keyword_raw` and `keyword_enriched` both have column@10 `54.17%`; keyword enrichment changes table recall/MRR but does not solve column recall alone in this sample.

Multi-query highlights:
- `keyword_enriched` improves table@5 over `keyword_raw`: `95.83%` vs `83.33%`; column@10 remains `83.33%`.
- `vector_raw` has column@10 `91.67%`; `vector_enriched` has column@10 `83.33%`.
- All hybrid variants reach table@5 `100.00%` and column@10 `83.33%`.
- Among hybrids, `hybrid_raw` has the strongest mrr_column in this sample (`0.3708`), while `hybrid_keyword_enriched_vector_raw` (`0.3500`) is better than full `hybrid_enriched` (`0.3090`).

## Latency Interpretation

The split timers confirm the earlier p95 confusion:

- Keyword recall is cheap: p95 is generally under `20ms`.
- Actual vector DB recall is also small: p95 is generally around `58-62ms`.
- Multi-query vector/hybrid p95 is dominated by online query embedding, not vector search:
  - `vector_raw/multi`: query embed p95 `1931.571ms`, vector recall p95 `60.168ms`.
  - `hybrid_raw/multi`: query embed p95 `2909.581ms`, vector recall p95 `57.441ms`.
  - `hybrid_enriched/multi`: query embed p95 `1841.712ms`, vector recall p95 `62.212ms`.
- Merge/rerank are not the bottleneck: merge p95 is around `1ms`, rerank is `0ms` in this run.

So keyword p95 is much faster mainly because it does not pay the online query embedding cost. For fair end-to-end comparison, multi-query planner latency and per-expression query embedding latency both need to be counted.

## Current Reading

This run validates the test framework and profile matrix. It does not yet prove a final online choice.

Observed on 24 cases / 3 DBs:
- AI enrichment helps keyword table recall in multi-query mode.
- Putting AI fields into vector embeddings is mixed: it improves single-query vector quality in this sample, but weakens multi-query vector column recall.
- The most important mixed control, `keyword_enriched + vector_raw`, is now runnable and auditable. In this sample it does not clearly beat `hybrid_raw`, but it does beat full `hybrid_enriched` on multi-query column MRR.

## Caveats

`n=24` is larger than smoke but still modest. p95 is no longer just max, but it is still sensitive to a few slow provider calls. This run should be treated as a framework and directional result, not final product evidence.

This run used the current `multi` implementation: planner expressions are each sent through `db.search`. For vector and hybrid rows, that means every planner expression is embedded separately. It is valid as a diagnostic run for `multi_keyword_vector_expression_each`, but it does not answer whether production hybrid should use planner expressions for keyword search while embedding only the original user question for vector search.

Recommended next run:
- 40 cases / 5 DBs
- Same 8 variants
- Same staged latency metrics
- Keep raw/enriched corpora and embeddings prebuilt before all matrix cells
- Add explicit query policies, especially `multi_keyword_vector_question`, before using the results for a production recommendation
