# Spider Retrieval Profile Contrast Report

## Main Recommendation Candidates

| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | mrr_table | mrr_column | planner expr avg | q-embed calls avg | expr-embed calls avg | db.search calls avg | measured provider p95 | modeled online p95 | query embed p95 | keyword recall p95 | vector recall p95 | vector_available |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched_question | hybrid | multi | multi_keyword_vector_question | enriched | enriched | 24 | 100.00% | 91.67% | 0.9444 | 0.2917 | 4.0 | 1.0 | 0.0 | 5.0 | 1624.514 | 1647.08 | 458.226 | 14.017 | 13.884 | 1.0 |
| hybrid_enriched_question | hybrid | single | single_question | enriched | enriched | 24 | 91.67% | 87.50% | 0.9167 | 0.3552 | 0.0 | 1.0 | 0.0 | 1.0 | 417.257 | 434.072 | 417.257 | 10.048 | 11.819 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | multi | multi_keyword_vector_question | enriched | raw | 24 | 100.00% | 91.67% | 0.9444 | 0.2826 | 4.0 | 1.0 | 0.0 | 5.0 | 1619.833 | 1638.306 | 483.66 | 10.917 | 12.609 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | single | single_question | enriched | raw | 24 | 95.83% | 91.67% | 0.9132 | 0.3552 | 0.0 | 1.0 | 0.0 | 1.0 | 447.905 | 464.777 | 447.905 | 9.53 | 11.531 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | multi | multi_keyword_vector_question | raw | enriched | 24 | 91.67% | 91.67% | 0.9444 | 0.3021 | 4.0 | 1.0 | 0.0 | 5.0 | 1620.509 | 1637.864 | 531.136 | 9.719 | 12.609 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | single | single_question | raw | enriched | 24 | 91.67% | 79.17% | 0.9236 | 0.3761 | 0.0 | 1.0 | 0.0 | 1.0 | 453.156 | 467.402 | 453.156 | 8.236 | 11.971 | 1.0 |
| hybrid_raw_question | hybrid | multi | multi_keyword_vector_question | raw | raw | 24 | 91.67% | 91.67% | 0.9444 | 0.2965 | 4.0 | 1.0 | 0.0 | 5.0 | 1635.992 | 1653.533 | 418.765 | 11.594 | 12.661 | 1.0 |
| hybrid_raw_question | hybrid | single | single_question | raw | raw | 24 | 95.83% | 87.50% | 0.9132 | 0.3726 | 0.0 | 1.0 | 0.0 | 1.0 | 444.739 | 463.897 | 444.739 | 8.367 | 11.839 | 1.0 |
| keyword_enriched | keyword | multi | multi_keyword_vector_question | enriched | none | 24 | 100.00% | 91.67% | 0.9444 | 0.2847 | 4.0 | 0.0 | 0.0 | 4.0 | 1233.758 | 1242.423 | 0.0 | 9.425 | 0.0 | None |
| keyword_enriched | keyword | single | single_question | enriched | none | 24 | 87.50% | 62.50% | 0.8681 | 0.3646 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 7.401 | 0.0 | 7.326 | 0.0 | None |
| keyword_raw | keyword | multi | multi_keyword_vector_question | raw | none | 24 | 83.33% | 91.67% | 0.9444 | 0.3021 | 4.0 | 0.0 | 0.0 | 4.0 | 1233.758 | 1241.614 | 0.0 | 9.099 | 0.0 | None |
| keyword_raw | keyword | single | single_question | raw | none | 24 | 87.50% | 54.17% | 0.8403 | 0.3569 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 11.625 | 0.0 | 11.548 | 0.0 | None |
| vector_enriched | vector | multi | single_question | none | enriched | 24 | 100.00% | 87.50% | 0.9306 | 0.4201 | 0.0 | 1.0 | 0.0 | 1.0 | 449.69 | 459.219 | 449.69 | 0.0 | 13.402 | 1.0 |
| vector_enriched | vector | single | single_question | none | enriched | 24 | 100.00% | 87.50% | 0.9306 | 0.4201 | 0.0 | 1.0 | 0.0 | 1.0 | 509.4 | 518.28 | 509.4 | 0.0 | 13.149 | 1.0 |
| vector_raw | vector | multi | single_question | none | raw | 24 | 91.67% | 91.67% | 0.9514 | 0.3819 | 0.0 | 1.0 | 0.0 | 1.0 | 441.751 | 448.771 | 441.751 | 0.0 | 13.047 | 1.0 |
| vector_raw | vector | single | single_question | none | raw | 24 | 91.67% | 91.67% | 0.9514 | 0.3819 | 0.0 | 1.0 | 0.0 | 1.0 | 437.408 | 448.768 | 437.408 | 0.0 | 13.415 | 1.0 |

## Diagnostic / Stress Variants

These rows use `multi_keyword_vector_expression_each`, which embeds every planner expression. They are diagnostic/stress only and are excluded from the main recommendation table.

| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | expr-embed calls avg | measured provider p95 | modeled online p95 | query embed p95 |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched_expression_each | hybrid | multi | multi_keyword_vector_expression_each | enriched | enriched | 24 | 100.00% | 83.33% | 4.0 | 2769.38 | 2952.491 | 1859.774 |
| hybrid_enriched_expression_each | hybrid | single | single_question | enriched | enriched | 24 | 91.67% | 87.50% | 0.0 | 592.636 | 608.452 | 592.636 |
| hybrid_keyword_enriched_vector_raw_expression_each | hybrid | multi | multi_keyword_vector_expression_each | enriched | raw | 24 | 100.00% | 83.33% | 4.0 | 2773.764 | 2831.807 | 1670.683 |
| hybrid_keyword_enriched_vector_raw_expression_each | hybrid | single | single_question | enriched | raw | 24 | 95.83% | 91.67% | 0.0 | 422.382 | 437.115 | 422.382 |

## Notes

- Main hybrid policy uses planner expressions for keyword search and embeds the original question once for vector search.
- `multi_keyword_vector_expression_each` embeds every planner expression and is diagnostic/stress only.
- Planner warmup is reported in `prep_check.json` and excluded from per-case planner latency.
- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.
- `vector_recall_ms` excludes `query_embedding_ms`; query embedding is reported separately.
- Runs below 100 cases are smoke/directional, not final decision support.
