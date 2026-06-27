# Spider Retrieval AI-Enrichment Contrast Verification

Run date: 2026-06-27

## Scope

This run verifies a real-provider retrieval contrast across:

- schema corpus variants: `base`, `ai_enriched`
- retrievers: `keyword`, `vector`, `hybrid`
- query modes: `single`, `multi`
- cases: 12 Spider cases, sampled round-robin across 3 databases

The provider key was loaded from local environment configuration at `C:\Users\Lenovo\.dbfox\dbfox-eval.env`. No key value is stored in this report or committed artifacts.

## Test Set Design

Source cases: `D:\DBFoxData\spider\spider_data\dev_stratified_156.json`

Sampling:

- `DBFOX_EVAL_SAMPLE_STRATEGY=round_robin_db`
- `DBFOX_EVAL_CASE_LIMIT=12`
- `DBFOX_EVAL_DB_LIMIT=3`

Selected DB distribution:

| db_id | cases |
|---|---:|
| `concert_singer` | 4 |
| `pets_1` | 4 |
| `car_1` | 4 |

This avoids the previous file-head behavior where a small limit could test only `concert_singer`.

## Corpus And Embedding Prep

The runner materialized both corpus variants before measuring retrieval:

| variant | db_id | schema docs | AI metadata docs | embedding rows | docs = embeddings |
|---|---|---:|---:|---:|---|
| `base` | `concert_singer` | 25 | 0 | 25 | true |
| `base` | `pets_1` | 17 | 0 | 17 | true |
| `base` | `car_1` | 29 | 0 | 29 | true |
| `ai_enriched` | `concert_singer` | 25 | 25 | 25 | true |
| `ai_enriched` | `pets_1` | 17 | 17 | 17 | true |
| `ai_enriched` | `car_1` | 29 | 29 | 29 | true |

AI enrichment completed for all selected DBs:

| db_id | enriched tables | enrich latency ms |
|---|---:|---:|
| `concert_singer` | 4 | 38063.572 |
| `pets_1` | 3 | 27575.631 |
| `car_1` | 6 | 55983.410 |

## Stream Monitoring

Progress was written incrementally to `progress_events.jsonl`.

- total progress events: 378
- `case_start`: 144
- `case_done`: 144
- `run_done`: 1
- first event: `2026-06-27T05:19:18.949907+00:00`
- last event: `2026-06-27T05:23:55.975451+00:00`

This confirms the run is monitorable while executing, not only after final report generation.

## Results

| variant | retriever | query mode | table@5 | column@10 | mrr_table | mrr_column | planner p95 ms | query embedding p95 ms | retrieval p95 ms | e2e p95 ms |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `base` | `keyword` | `single` | 91.7% | 58.3% | 0.8750 | 0.4167 | 0.000 | 0.000 | 21.176 | 21.176 |
| `ai_enriched` | `keyword` | `single` | 91.7% | 75.0% | 0.8611 | 0.4167 | 0.000 | 0.000 | 13.356 | 13.356 |
| `base` | `keyword` | `multi` | 100.0% | 91.7% | 1.0000 | 0.2917 | 21832.129 | 0.000 | 23.152 | 21855.281 |
| `ai_enriched` | `keyword` | `multi` | 100.0% | 100.0% | 1.0000 | 0.2639 | 21832.129 | 0.000 | 19.021 | 21845.331 |
| `base` | `vector` | `single` | 100.0% | 100.0% | 1.0000 | 0.3472 | 0.000 | 498.558 | 514.132 | 514.132 |
| `ai_enriched` | `vector` | `single` | 100.0% | 100.0% | 0.8889 | 0.2847 | 0.000 | 549.835 | 561.309 | 561.309 |
| `base` | `vector` | `multi` | 100.0% | 100.0% | 1.0000 | 0.5000 | 21832.129 | 1967.205 | 2025.698 | 23774.927 |
| `ai_enriched` | `vector` | `multi` | 100.0% | 83.3% | 0.9028 | 0.3333 | 21832.129 | 1879.262 | 1920.197 | 23709.657 |
| `base` | `hybrid` | `single` | 100.0% | 100.0% | 0.9375 | 0.3944 | 0.000 | 526.606 | 550.072 | 550.072 |
| `ai_enriched` | `hybrid` | `single` | 91.7% | 91.7% | 0.9306 | 0.3750 | 0.000 | 471.130 | 491.225 | 491.225 |
| `base` | `hybrid` | `multi` | 100.0% | 83.3% | 1.0000 | 0.4028 | 21832.129 | 1942.105 | 2010.606 | 23842.735 |
| `ai_enriched` | `hybrid` | `multi` | 100.0% | 83.3% | 1.0000 | 0.3472 | 21832.129 | 1790.822 | 1844.068 | 23581.727 |

## Interpretation

The contrast is now measuring real corpus differences:

- `base` schema docs have no AI metadata fields.
- `ai_enriched` schema docs include AI descriptions/tags/aliases/business terms.
- embeddings are rebuilt after each corpus variant, so vector and hybrid retrieval also compare base-vs-enriched corpora.

Latency accounting is fairer than the earlier benchmark:

- `e2e p95` includes LLM multi-query planning time.
- `retrieval p95`, `query embedding p95`, and `planner p95` are kept separate for diagnosis.
- multi-query recall gains should be read together with planner p95, which is the dominant latency in this run.

Observed effect on this 12-case sample:

- AI enrichment improved keyword column recall: `single` 58.3% -> 75.0%, `multi` 91.7% -> 100.0%.
- Vector single stayed at 100.0% column recall, but AI enrichment reduced MRR and vector multi column recall in this small sample.
- Hybrid did not show a clear enrichment win here; its single-mode recall dropped slightly, while multi-mode column recall stayed 83.3%.

Conclusion: the pipeline is now capable of a real base-vs-AI-enriched comparison, and the result is mixed rather than automatically positive. The next larger run should use the same `round_robin_db` strategy with a larger case count, for example 24 cases across the first 3 DBs or 40 cases across 5 DBs.
