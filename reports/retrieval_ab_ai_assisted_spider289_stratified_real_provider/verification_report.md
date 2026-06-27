# Spider289 Stratified AI-assisted retrieval verification report

## Scope

- Branch/worktree: `evaluation/spider-retrieval-benchmark`
- Dataset used: `D:\DBFoxData\spider\spider_data\dev_stratified_289.json`
- Sampling method: Spider dev, max 15 cases per `db_id`
- Case count: 289
- Unique DBs: 20
- Mode: `ai-assisted-retrieval`
- Variants: `keyword`, `vector`, `hybrid`
- Query planning: real LLM planner, `qwen-plus`
- Embedding provider: real DashScope OpenAI-compatible endpoint
- Embedding model/dimension: `text-embedding-v4`, 1024
- Top K: 20
- Runtime: about 35 minutes on this machine

Additional local sample files prepared under the Spider data root:

| file | cases | db coverage | purpose |
|---|---:|---:|---|
| `dev_stratified_156.json` | 156 | 20 DBs | medium smoke, max 8 cases/db |
| `dev_stratified_289.json` | 289 | 20 DBs | expanded run, max 15 cases/db |
| `dev_stratified_373.json` | 373 | 20 DBs | larger follow-up, max 20 cases/db |
| `dev.json` | 1034 | 20 DBs | full Spider dev |

The stratified files are local generated test inputs, not committed repo fixtures.

## Preparation Checks

Schema docs and embeddings were prepared before retrieval:

| check | value |
|---|---:|
| datasources | 20 |
| schema tables | 80 |
| schema columns | 439 |
| schema search docs | 519 |
| embedding rows | 519 |
| docs equal embeddings | true |
| vector/hybrid smoke checks | 40/40 available |

This confirms the vector and hybrid results were not produced by the deterministic local embedding stub.

## Results

| variant | cases | table_recall@5 | column_recall@10 | vector_available | db.search calls | retrieval_miss | p95 retrieval latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| keyword | 289 | 94.12% | 69.20% | n/a | 1156 | 91 | 27.783 ms |
| vector | 289 | 92.39% | 68.86% | 100.00% | 1156 | 93 | 3018.709 ms |
| hybrid | 289 | 94.81% | 70.24% | 100.00% | 1156 | 89 | 3171.827 ms |

Compared with keyword, hybrid is slightly better on this broader sample:

- table recall: +0.69 percentage points
- column recall: +1.04 percentage points
- retrieval misses: 2 fewer cases

Vector alone still underperforms keyword slightly:

- table recall: -1.73 percentage points
- column recall: -0.34 percentage points
- retrieval misses: 2 more cases

## Miss Shape

Top retrieval-miss DBs:

| variant | top miss DBs |
|---|---|
| keyword | `world_1` 13/15, `flight_2` 9/15, `battle_death` 9/15, `car_1` 8/15, `tvshow` 8/15 |
| vector | `world_1` 15/15, `flight_2` 9/15, `tvshow` 8/15, `dog_kennels` 8/15, `pets_1` 7/15 |
| hybrid | `world_1` 15/15, `flight_2` 9/15, `tvshow` 9/15, `pets_1` 7/15, `car_1` 7/15 |

`world_1` is the main stress case in this expanded sample. The high miss count there suggests the schema-search text and synonym coverage still need work for geography-oriented schemas and table/column naming variants.

## Interpretation

- Environment readiness is no longer the blocker for vector/hybrid: docs and embeddings match, and vector availability is 100%.
- Hybrid starts to beat keyword once the sample covers all 20 Spider dev databases, but the margin is still small.
- Vector-only retrieval is not enough; it adds latency and still misses key tables on some schemas.
- Column recall remains the weakest shared metric. The next quality work should enrich schema docs with relationship, foreign-key, and business-term text rather than only tuning vector ranking.
- Full dev should wait until the eval runner has progress logging and query-embedding timeout/cache support; otherwise the 1034-case run will be slow and hard to diagnose.

## Test Framework Findings

- The runner writes most outputs only at the end, so long real-provider runs have poor observability.
- A failed first launch showed that writing `run.log` inside the report directory conflicts with runner cleanup on Windows. Logs should stay outside the report dir, or runner cleanup should preserve known log files.
- `embed_texts()` builds the OpenAI-compatible embedding client without an explicit timeout. Query embeddings are requested during vector/hybrid retrieval, so larger test sets can wait on provider calls for a long time.
- Each case generated 4 planner expressions, so each variant made 4 `db.search` calls per case.

## Artifacts

- `prep_check.json`
- `search_plans.json`
- `metadata.sqlite`
- `spider_keyword_vector_hybrid_summary.json`
- `spider_keyword_vector_hybrid_cases.csv`
- `spider_keyword_vector_hybrid_cases.jsonl`
- `spider_keyword_vector_hybrid_report.md`

## Secret Check

Secret-pattern scan was run against the generated report directory and the external run log. No `sk-...` provider-key pattern was found.
