# Spider Retrieval Profile Contrast Report

## Main Recommendation Candidates

| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | mrr_table | mrr_column | planner expr avg | q-embed calls avg | expr-embed calls avg | db.search calls avg | measured provider p95 | modeled online p95 | query embed p95 | keyword recall p95 | vector recall p95 | vector_available |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched_question | hybrid | multi | multi_keyword_vector_question | enriched | enriched | 40 | 100.00% | 72.50% | 0.9542 | 0.3396 | 4.0 | 1.0 | 0.0 | 5.0 | 1565.844 | 1581.571 | 420.409 | 10.935 | 11.412 | 1.0 |
| hybrid_enriched_question | hybrid | single | single_question | enriched | enriched | 40 | 95.00% | 65.00% | 0.9083 | 0.4290 | 0.0 | 1.0 | 0.0 | 1.0 | 424.113 | 439.226 | 424.113 | 8.164 | 11.757 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | multi | multi_keyword_vector_question | enriched | raw | 40 | 100.00% | 75.00% | 0.9542 | 0.3404 | 4.0 | 1.0 | 0.0 | 5.0 | 1503.963 | 1527.468 | 448.831 | 10.221 | 11.627 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | single | single_question | enriched | raw | 40 | 97.50% | 70.00% | 0.9050 | 0.4273 | 0.0 | 1.0 | 0.0 | 1.0 | 422.379 | 439.724 | 422.379 | 8.753 | 11.71 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | multi | multi_keyword_vector_question | raw | enriched | 40 | 95.00% | 72.50% | 0.9542 | 0.3583 | 4.0 | 1.0 | 0.0 | 5.0 | 1519.548 | 1535.162 | 418.873 | 9.397 | 11.791 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | single | single_question | raw | enriched | 40 | 95.00% | 65.00% | 0.9104 | 0.4356 | 0.0 | 1.0 | 0.0 | 1.0 | 417.878 | 428.619 | 417.878 | 7.724 | 12.03 | 1.0 |
| hybrid_raw_question | hybrid | multi | multi_keyword_vector_question | raw | raw | 40 | 95.00% | 72.50% | 0.9542 | 0.3550 | 4.0 | 1.0 | 0.0 | 5.0 | 1540.93 | 1556.432 | 437.118 | 9.731 | 10.96 | 1.0 |
| hybrid_raw_question | hybrid | single | single_question | raw | raw | 40 | 97.50% | 70.00% | 0.9029 | 0.4402 | 0.0 | 1.0 | 0.0 | 1.0 | 432.006 | 444.653 | 432.006 | 8.599 | 11.962 | 1.0 |
| keyword_enriched | keyword | multi | multi_keyword_vector_question | enriched | none | 40 | 100.00% | 75.00% | 0.9542 | 0.3333 | 4.0 | 0.0 | 0.0 | 4.0 | 1123.55 | 1130.217 | 0.0 | 9.217 | 0.0 | None |
| keyword_enriched | keyword | single | single_question | enriched | none | 40 | 87.50% | 42.50% | 0.8458 | 0.3904 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 6.348 | 0.0 | 6.279 | 0.0 | None |
| keyword_raw | keyword | multi | multi_keyword_vector_question | raw | none | 40 | 90.00% | 70.00% | 0.9542 | 0.3583 | 4.0 | 0.0 | 0.0 | 4.0 | 1123.55 | 1129.958 | 0.0 | 8.486 | 0.0 | None |
| keyword_raw | keyword | single | single_question | raw | none | 40 | 87.50% | 42.50% | 0.8417 | 0.4308 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 11.602 | 0.0 | 11.53 | 0.0 | None |
| vector_enriched | vector | multi | single_question | none | enriched | 40 | 100.00% | 75.00% | 0.9542 | 0.4787 | 0.0 | 1.0 | 0.0 | 1.0 | 417.112 | 425.215 | 417.112 | 0.0 | 13.344 | 1.0 |
| vector_enriched | vector | single | single_question | none | enriched | 40 | 100.00% | 75.00% | 0.9542 | 0.4787 | 0.0 | 1.0 | 0.0 | 1.0 | 411.975 | 421.661 | 411.975 | 0.0 | 13.043 | 1.0 |
| vector_raw | vector | multi | single_question | none | raw | 40 | 95.00% | 75.00% | 0.9458 | 0.4917 | 0.0 | 1.0 | 0.0 | 1.0 | 420.82 | 429.318 | 420.82 | 0.0 | 12.53 | 1.0 |
| vector_raw | vector | single | single_question | none | raw | 40 | 95.00% | 75.00% | 0.9458 | 0.4917 | 0.0 | 1.0 | 0.0 | 1.0 | 422.842 | 429.347 | 422.842 | 0.0 | 12.755 | 1.0 |

## Diagnostic / Stress Variants

These rows use `multi_keyword_vector_expression_each`, which embeds every planner expression. They are diagnostic/stress only and are excluded from the main recommendation table.

| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | expr-embed calls avg | measured provider p95 | modeled online p95 | query embed p95 |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched_expression_each | hybrid | multi | multi_keyword_vector_expression_each | enriched | enriched | 40 | 100.00% | 62.50% | 4.0 | 2688.391 | 2733.144 | 1694.971 |
| hybrid_enriched_expression_each | hybrid | single | single_question | enriched | enriched | 40 | 95.00% | 65.00% | 0.0 | 422.776 | 433.561 | 422.776 |
| hybrid_keyword_enriched_vector_raw_expression_each | hybrid | multi | multi_keyword_vector_expression_each | enriched | raw | 40 | 100.00% | 70.00% | 4.0 | 2760.706 | 2811.511 | 1663.517 |
| hybrid_keyword_enriched_vector_raw_expression_each | hybrid | single | single_question | enriched | raw | 40 | 97.50% | 70.00% | 0.0 | 484.908 | 500.012 | 484.908 |

## Notes

- Main hybrid policy uses planner expressions for keyword search and embeds the original question once for vector search.
- `multi_keyword_vector_expression_each` embeds every planner expression and is diagnostic/stress only.
- Planner warmup is reported in `prep_check.json` and excluded from per-case planner latency.
- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.
- `vector_recall_ms` excludes `query_embedding_ms`; query embedding is reported separately.
- Runs below 100 cases are smoke/directional, not final decision support.
