# Full Spider Retrieval Benchmark Verification Report

## Scope

- Dataset: Spider dev subset loaded from local Spider databases.
- Case count: 1034 questions across 20 databases.
- Matrix: 8 main retrieval variants x 2 query modes = 16544 case rows.
- Diagnostics: `multi_keyword_vector_expression_each` was intentionally not included in this full run. Earlier smoke runs label it as diagnostic/stress only; it is not part of the main recommendation table.
- Provider: real Qwen/Alibaba embedding and planner calls, with corpus embeddings prepared before the benchmark run.

## Acceptance Verification

| Check | Result |
|---|---:|
| Case rows completed | 16544 |
| Summary rows completed | 16 |
| Final progress event | `run_done` |
| Corpus profiles prepared | 40 |
| Docs equal embeddings | pass |
| Raw corpus AI metadata count | 0 for all raw corpora |
| Vector recall timing excludes query embedding | pass |
| Query embedding timing reported separately | pass |
| Runs below 100 cases labelled smoke/directional | pass |

For `hybrid_keyword_enriched_vector_raw_question` in multi mode:

| Field | Value |
|---|---|
| keyword corpus profile | `enriched` |
| vector corpus profile | `raw` |
| query policy | `multi_keyword_vector_question` |
| vector query | original question only |
| vector expression count | 1 |
| question embedding call count | 1 |
| expression embedding call count | 0 |
| db search call count | 5 |

## Corpus Caveat

All raw/enriched document corpora and embeddings were generated and row counts match. One enriched database needs a coverage caveat: `wta_1` has 46 schema search docs and 46 embeddings, but only 3 docs have direct AI metadata fields populated. Inspection shows those 3 are table docs; column docs remain raw column docs. This does not invalidate the retrieval run, but it means "AI metadata coverage is complete" is not true for `wta_1`.

## Main Multi-Query Results

| variant | keyword corpus | vector corpus | table@5 | column@10 | mrr_table | mrr_column | q-embed calls | expr-embed calls | db.search calls | provider p95 ms | modeled online p95 ms | query embedding p95 ms | vector recall p95 ms |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| keyword_raw | raw | none | 90.43% | 58.32% | 0.9561 | 0.3584 | 0.0 | 0.0 | 4.0 | 1152.304 | 1160.279 | 0.000 | 0.000 |
| keyword_enriched | enriched | none | 92.55% | 61.70% | 0.9584 | 0.3614 | 0.0 | 0.0 | 4.0 | 1152.304 | 1160.957 | 0.000 | 0.000 |
| vector_raw | none | raw | 86.46% | 59.57% | 0.9739 | 0.5743 | 1.0 | 0.0 | 1.0 | 421.473 | 434.868 | 421.473 | 22.979 |
| vector_enriched | none | enriched | 90.62% | 60.93% | 0.9618 | 0.5644 | 1.0 | 0.0 | 1.0 | 428.799 | 440.326 | 428.799 | 23.359 |
| hybrid_raw_question | raw | raw | 92.36% | 62.57% | 0.9638 | 0.3709 | 1.0 | 0.0 | 5.0 | 1561.042 | 1577.551 | 434.324 | 22.501 |
| hybrid_keyword_enriched_vector_raw_question | enriched | raw | 94.58% | 64.41% | 0.9631 | 0.3733 | 1.0 | 0.0 | 5.0 | 1550.178 | 1570.347 | 425.532 | 22.531 |
| hybrid_keyword_raw_vector_enriched_question | raw | enriched | 91.68% | 62.96% | 0.9630 | 0.3760 | 1.0 | 0.0 | 5.0 | 1544.416 | 1565.284 | 427.234 | 23.141 |
| hybrid_enriched_question | enriched | enriched | 94.00% | 64.89% | 0.9612 | 0.3756 | 1.0 | 0.0 | 5.0 | 1538.126 | 1557.948 | 426.178 | 22.883 |

## Interpretation

1. Keyword enrichment helps consistently. Compared with `keyword_raw`, `keyword_enriched` improves table@5 by 2.12 percentage points and column@10 by 3.38 percentage points.
2. Vector enrichment improves recall but slightly hurts ranking. Compared with `vector_raw`, `vector_enriched` improves table@5 by 4.16 points and column@10 by 1.36 points, while MRR drops from 0.9739 to 0.9618 for tables and from 0.5743 to 0.5644 for columns.
3. Hybrid is the best main online shape for table recall. The strongest table@5 row is `hybrid_keyword_enriched_vector_raw_question` at 94.58%.
4. Full enriched hybrid is the strongest column@10 row at 64.89%, but it is only 0.48 points ahead of `keyword_enriched + vector_raw`, while table@5 is 0.58 points lower.
5. The corrected latency accounting is working: vector/hybrid query embedding p95 is around 0.42s, while vector DB recall p95 is around 22-23ms. Main hybrid modeled online p95 is around 1.56s, dominated by planner plus one question embedding call.

## Recommendation

Use `hybrid_keyword_enriched_vector_raw_question` as the safer production default: planner-generated keyword expressions search enriched schema docs, vector search embeds only the original user question, and vector corpus stays raw. It gives the best table recall while avoiding expression embedding and avoiding direct AI metadata noise in vector embeddings.

Keep `hybrid_enriched_question` as a close alternative if the product metric prioritizes column@10 over table@5. The difference is small enough that final choice should be validated against downstream SQL execution accuracy, not schema retrieval alone.

## Artifacts

- Main machine report: `contrast_report.md`
- Structured summary: `contrast_summary.json`
- Per-case rows: `contrast_cases.jsonl` and `contrast_cases.csv`
- Corpus/prep verification: `prep_check.json`
- Stream/progress log: `progress_events.jsonl`
