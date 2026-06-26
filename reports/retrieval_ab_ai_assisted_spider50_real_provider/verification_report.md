# Spider AI-assisted retrieval verification report

## Scope

- Dataset: `D:\DBFoxData\spider\spider_data\dev.json`
- Case limit: first 50 Spider dev cases
- Unique DBs covered in this slice: `concert_singer`, `pets_1`
- Mode: `ai-assisted-retrieval`
- Variants compared: `keyword`, `vector`, `hybrid`
- Query planning: real LLM planner, `qwen-plus`
- Embedding provider: real DashScope OpenAI-compatible endpoint
- Embedding model: `text-embedding-v4`
- Embedding dimension: 1024
- Top K: 20

Note: this is larger than the tiny fixture, but it is still not a full Spider eval. The first 50 Spider dev rows are concentrated in only 2 databases, so the result should be treated as a focused smoke/regression run, not a final global benchmark.

## Preparation checks

Schema docs and embeddings were prepared before retrieval:

| db_id | schema tables | schema columns | schema search docs | embedding rows | stale embeddings | docs equal embeddings |
|---|---:|---:|---:|---:|---:|---|
| concert_singer | 4 | 21 | 25 | 25 | 0 | true |
| pets_1 | 3 | 14 | 17 | 17 | 0 | true |

Vector smoke checks passed for both DBs:

| db_id | mode | vector_available | total_matches |
|---|---|---:|---:|
| concert_singer | vector | true | 20 |
| concert_singer | hybrid | true | 20 |
| pets_1 | vector | true | 17 |
| pets_1 | hybrid | true | 18 |

This means the Spider50 vector/hybrid result is not using the deterministic local stub. The embedding path was available and populated.

## Results

| variant | cases | table_recall@5 | column_recall@10 | vector_available | db.search calls | retrieval_miss | p95 retrieval latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| keyword | 50 | 100.0% | 74.0% | n/a | 200 | 13 | 15.632 ms |
| vector | 50 | 90.0% | 72.0% | 100.0% | 200 | 15 | 2330.925 ms |
| hybrid | 50 | 92.0% | 72.0% | 100.0% | 200 | 15 | 3675.797 ms |

Each variant made 200 `db.search` calls because each case used up to 4 AI-planned search expressions and then evaluated the fused result.

## Miss shape

| variant | table hit | column hit | count |
|---|---:|---:|---:|
| keyword | true | true | 37 |
| keyword | true | false | 13 |
| vector | true | true | 35 |
| vector | true | false | 10 |
| vector | false | true | 1 |
| vector | false | false | 4 |
| hybrid | true | true | 35 |
| hybrid | true | false | 11 |
| hybrid | false | true | 1 |
| hybrid | false | false | 3 |

Observations:

- `keyword` found all required tables in this slice, but missed required columns in 13 cases.
- `vector` and `hybrid` had real vector availability, but still introduced table misses.
- The misses are mostly in `concert_singer`, especially questions involving `stadium`, `concert`, and join/aggregation semantics.
- `hybrid` did not beat `keyword` on this slice. The current fusion is probably letting vector-side noise drag down otherwise strong keyword hits.

## Interpretation

The environment is no longer the primary blocker for vector/hybrid:

- Schema docs exist.
- Embedding rows match schema docs.
- Vector availability is 100% for vector and hybrid.
- Real provider calls were used.

The remaining issue is retrieval quality/design:

- Column recall is the weak point for all three variants.
- Vector search is not yet improving recall on this Spider slice.
- Hybrid needs better weighting or fusion rules before it can reliably dominate keyword.
- Schema docs may need richer relationship/foreign-key text, because several misses are join-heavy or aggregation-heavy.
- AI-planned search expressions are real multi-query prompts now, but they may still over-focus on natural-language concepts and under-represent exact schema identifiers.

## Artifacts

- `prep_check.json`
- `search_plans.json`
- `metadata.sqlite`
- `spider_keyword_vector_hybrid_summary.json`
- `spider_keyword_vector_hybrid_cases.csv`
- `spider_keyword_vector_hybrid_cases.jsonl`
- `spider_keyword_vector_hybrid_report.md`

## Code verification

Related test subset:

```powershell
python -m pytest -p no:cacheprovider --basetemp D:\tmp_codex_pytest engine/tests/test_retrieval_ab_config_report_runner.py engine/tests/test_retrieval_ab_metrics.py engine/tests/test_retrieval_ab_variants.py engine/tests/test_schema_vector_search.py -q
```

Result: 35 passed, 10 warnings.

The normal pytest cache path could not be used because the C drive reported 0 bytes free during this run. The successful run used D drive temp storage and disabled pytest cache writing.

Secret scan: no provider key string was found in the touched `engine` files or generated report directories.
