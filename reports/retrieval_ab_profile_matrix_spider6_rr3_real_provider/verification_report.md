# Spider Retrieval Profile Matrix Verification

Run date: 2026-06-27

## What This Run Tests

This run prepares all selected test-set databases in two corpus profiles before retrieval:

- `raw`: schema docs and embeddings without AI semantic fields
- `enriched`: schema docs and embeddings with AI descriptions/tags/aliases/business terms

Retrieval then runs six explicit methods:

| method | retriever | corpus |
|---|---|---|
| `keyword_raw` | keyword | raw |
| `vector_raw` | vector | raw |
| `keyword_enriched` | keyword | enriched |
| `vector_enriched` | vector | enriched |
| `hybrid_raw` | hybrid | raw |
| `hybrid_enriched` | hybrid | enriched |

This no longer relies on sequentially overwriting a single datasource. Raw and enriched corpora coexist in `metadata.sqlite`.

## Test Set

Source: `D:\DBFoxData\spider\spider_data\dev_stratified_156.json`

Sampling:

- `DBFOX_EVAL_SAMPLE_STRATEGY=round_robin_db`
- `DBFOX_EVAL_CASE_LIMIT=6`
- `DBFOX_EVAL_DB_LIMIT=3`

Selected DBs:

| db_id | cases |
|---|---:|
| `concert_singer` | 2 |
| `pets_1` | 2 |
| `car_1` | 2 |

## Preparation Check

Prepared datasources:

| db_id | raw datasource | enriched datasource |
|---|---|---|
| `concert_singer` | `spider_concert_singer_raw_5278d285` | `spider_concert_singer_enriched_25ca6da5` |
| `pets_1` | `spider_pets_1_raw_1b49b58b` | `spider_pets_1_enriched_4cfec849` |
| `car_1` | `spider_car_1_raw_70701fae` | `spider_car_1_enriched_4816c7c4` |

Corpus and embedding status:

| corpus | db_id | docs | AI metadata docs | embedding rows | docs = embeddings |
|---|---|---:|---:|---:|---|
| raw | `concert_singer` | 25 | 0 | 25 | true |
| raw | `pets_1` | 17 | 0 | 17 | true |
| raw | `car_1` | 29 | 0 | 29 | true |
| enriched | `concert_singer` | 25 | 25 | 25 | true |
| enriched | `pets_1` | 17 | 17 | 17 | true |
| enriched | `car_1` | 29 | 29 | 29 | true |

AI enrichment ran only against the enriched datasources:

| db_id | enriched tables | enrich latency ms |
|---|---:|---:|
| `concert_singer` | 4 | 42170.526 |
| `pets_1` | 3 | 27462.190 |
| `car_1` | 6 | 52157.238 |

## Query Planning And Timing

The first client warmup is separated from case latency:

- `planner_warmup_ms`: 17763.651
- `planner_warmup_in_case_latency`: false

Per-case multi-query planning:

| case_id | db_id | planner ms | expressions |
|---|---|---:|---:|
| `spider_concert_singer_001` | `concert_singer` | 881.510 | 4 |
| `spider_pets_1_002` | `pets_1` | 855.567 | 4 |
| `spider_car_1_003` | `car_1` | 749.977 | 4 |
| `spider_concert_singer_004` | `concert_singer` | 818.483 | 4 |
| `spider_pets_1_005` | `pets_1` | 830.959 | 4 |
| `spider_car_1_006` | `car_1` | 787.642 | 4 |

Progress stream:

- total events: 229
- `case_done`: 72
- `datasource_sync_done`: 6
- `corpus_prepare_done`: 6
- `run_done`: 1

## Result Summary

| method | mode | table@5 | column@10 | mrr_table | mrr_column | planner p50/p95/max | retrieval p50/p95/max | e2e p50/p95/max |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `keyword_raw` | single | 83.3% | 100.0% | 0.7500 | 0.1667 | 0.000/0.000/0.000 | 9.598/15.851/15.851 | 9.598/15.851/15.851 |
| `keyword_raw` | multi | 100.0% | 100.0% | 1.0000 | 0.1389 | 824.721/881.510/881.510 | 8.788/14.379/14.379 | 832.343/895.889/895.889 |
| `keyword_enriched` | single | 83.3% | 100.0% | 0.8333 | 0.1667 | 0.000/0.000/0.000 | 6.005/10.072/10.072 | 6.005/10.072/10.072 |
| `keyword_enriched` | multi | 100.0% | 100.0% | 1.0000 | 0.1389 | 824.721/881.510/881.510 | 9.500/12.116/12.116 | 836.186/887.967/887.967 |
| `vector_raw` | single | 100.0% | 100.0% | 1.0000 | 0.1667 | 0.000/0.000/0.000 | 471.450/488.246/488.246 | 471.450/488.246/488.246 |
| `vector_raw` | multi | 100.0% | 100.0% | 1.0000 | 0.2500 | 824.721/881.510/881.510 | 1890.454/1949.692/1949.692 | 2711.685/2743.732/2743.732 |
| `vector_enriched` | single | 100.0% | 100.0% | 0.7778 | 0.1389 | 0.000/0.000/0.000 | 554.430/2030.610/2030.610 | 554.430/2030.610/2030.610 |
| `vector_enriched` | multi | 100.0% | 100.0% | 0.8056 | 0.1667 | 824.721/881.510/881.510 | 1932.229/2905.639/2905.639 | 2766.806/3655.616/3655.616 |
| `hybrid_raw` | single | 100.0% | 100.0% | 0.8750 | 0.1667 | 0.000/0.000/0.000 | 479.939/569.323/569.323 | 479.939/569.323/569.323 |
| `hybrid_raw` | multi | 100.0% | 100.0% | 1.0000 | 0.1667 | 824.721/881.510/881.510 | 1931.784/1970.421/1970.421 | 2741.084/2837.265/2837.265 |
| `hybrid_enriched` | single | 83.3% | 100.0% | 0.8611 | 0.1667 | 0.000/0.000/0.000 | 458.255/468.737/468.737 | 458.255/468.737/468.737 |
| `hybrid_enriched` | multi | 100.0% | 100.0% | 1.0000 | 0.1667 | 824.721/881.510/881.510 | 1850.990/1911.040/1911.040 | 2624.020/2792.550/2792.550 |

## Interpretation

This is a smoke-sized matrix, so recall is saturated on many rows. It verifies the method rather than deciding final quality.

Observed in this sample:

- The corpus-preparation design is now correct: raw and enriched docs plus embeddings exist at the same time.
- Planner warmup is no longer contaminating per-case planner latency.
- `keyword_enriched` improves table MRR in single mode versus `keyword_raw`.
- `vector_enriched` has lower table MRR than `vector_raw` on this sample, which supports the concern that semantic enrichment may add embedding noise.
- `hybrid_enriched` is faster than `hybrid_raw` here, but table recall drops in single mode. Larger samples are needed before treating that as a stable effect.

Next larger run should keep this exact preparation model and increase to at least 24 cases across 3 DBs, then 40 cases across 5 DBs.
