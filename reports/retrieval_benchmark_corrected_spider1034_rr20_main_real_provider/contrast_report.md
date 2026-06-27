# Spider Retrieval Profile Contrast Report

## Main Recommendation Candidates

| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | mrr_table | mrr_column | planner expr avg | q-embed calls avg | expr-embed calls avg | db.search calls avg | measured provider p95 | modeled online p95 | query embed p95 | keyword recall p95 | vector recall p95 | vector_available |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched_question | hybrid | multi | multi_keyword_vector_question | enriched | enriched | 1034 | 94.00% | 64.89% | 0.9612 | 0.3756 | 4.0 | 1.0 | 0.0 | 5.0 | 1538.126 | 1557.948 | 426.178 | 11.949 | 22.883 | 1.0 |
| hybrid_enriched_question | hybrid | single | single_question | enriched | enriched | 1034 | 92.55% | 57.35% | 0.9260 | 0.3837 | 0.0 | 1.0 | 0.0 | 1.0 | 447.747 | 471.23 | 447.747 | 9.45 | 22.891 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | multi | multi_keyword_vector_question | enriched | raw | 1034 | 94.58% | 64.41% | 0.9631 | 0.3733 | 4.0 | 1.0 | 0.0 | 5.0 | 1550.178 | 1570.347 | 425.532 | 12.027 | 22.531 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | single | single_question | enriched | raw | 1034 | 92.75% | 58.22% | 0.9354 | 0.3839 | 0.0 | 1.0 | 0.0 | 1.0 | 423.092 | 445.395 | 423.092 | 9.606 | 22.51 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | multi | multi_keyword_vector_question | raw | enriched | 1034 | 91.68% | 62.96% | 0.9630 | 0.3760 | 4.0 | 1.0 | 0.0 | 5.0 | 1544.416 | 1565.284 | 427.234 | 10.597 | 23.141 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | single | single_question | raw | enriched | 1034 | 91.59% | 56.58% | 0.9355 | 0.3838 | 0.0 | 1.0 | 0.0 | 1.0 | 424.902 | 445.225 | 424.902 | 8.042 | 22.992 | 1.0 |
| hybrid_raw_question | hybrid | multi | multi_keyword_vector_question | raw | raw | 1034 | 92.36% | 62.57% | 0.9638 | 0.3709 | 4.0 | 1.0 | 0.0 | 5.0 | 1561.042 | 1577.551 | 434.324 | 10.549 | 22.501 | 1.0 |
| hybrid_raw_question | hybrid | single | single_question | raw | raw | 1034 | 91.20% | 57.06% | 0.9428 | 0.3878 | 0.0 | 1.0 | 0.0 | 1.0 | 434.391 | 452.159 | 434.391 | 8.222 | 22.276 | 1.0 |
| keyword_enriched | keyword | multi | multi_keyword_vector_question | enriched | none | 1034 | 92.55% | 61.70% | 0.9584 | 0.3614 | 4.0 | 0.0 | 0.0 | 4.0 | 1152.304 | 1160.957 | 0.0 | 10.544 | 0.0 | None |
| keyword_enriched | keyword | single | single_question | enriched | none | 1034 | 85.98% | 43.71% | 0.8798 | 0.3422 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 7.946 | 0.0 | 7.877 | 0.0 | None |
| keyword_raw | keyword | multi | multi_keyword_vector_question | raw | none | 1034 | 90.43% | 58.32% | 0.9561 | 0.3584 | 4.0 | 0.0 | 0.0 | 4.0 | 1152.304 | 1160.279 | 0.0 | 9.156 | 0.0 | None |
| keyword_raw | keyword | single | single_question | raw | none | 1034 | 84.04% | 42.26% | 0.8932 | 0.3692 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 7.188 | 0.0 | 7.063 | 0.0 | None |
| vector_enriched | vector | multi | single_question | none | enriched | 1034 | 90.62% | 60.93% | 0.9618 | 0.5644 | 0.0 | 1.0 | 0.0 | 1.0 | 428.799 | 440.326 | 428.799 | 0.0 | 23.359 | 1.0 |
| vector_enriched | vector | single | single_question | none | enriched | 1034 | 90.62% | 60.93% | 0.9618 | 0.5644 | 0.0 | 1.0 | 0.0 | 1.0 | 425.068 | 438.491 | 425.068 | 0.0 | 23.206 | 1.0 |
| vector_raw | vector | multi | single_question | none | raw | 1034 | 86.46% | 59.57% | 0.9739 | 0.5743 | 0.0 | 1.0 | 0.0 | 1.0 | 421.473 | 434.868 | 421.473 | 0.0 | 22.979 | 1.0 |
| vector_raw | vector | single | single_question | none | raw | 1034 | 86.46% | 59.57% | 0.9739 | 0.5743 | 0.0 | 1.0 | 0.0 | 1.0 | 437.345 | 448.172 | 437.345 | 0.0 | 22.63 | 1.0 |

## Notes

- Main hybrid policy uses planner expressions for keyword search and embeds the original question once for vector search.
- `multi_keyword_vector_expression_each` embeds every planner expression and is diagnostic/stress only.
- Planner warmup is reported in `prep_check.json` and excluded from per-case planner latency.
- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.
- `vector_recall_ms` excludes `query_embedding_ms`; query embedding is reported separately.
- Runs below 100 cases are smoke/directional, not final decision support.
