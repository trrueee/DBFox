# Spider Retrieval Profile Contrast Report

## Main Recommendation Candidates

| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | mrr_table | mrr_column | planner expr avg | q-embed calls avg | expr-embed calls avg | db.search calls avg | measured provider p95 | modeled online p95 | query embed p95 | keyword recall p95 | vector recall p95 | vector_available |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched_question | hybrid | multi | multi_keyword_vector_question | enriched | enriched | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 4.0 | 1.0 | 0.0 | 5.0 | 1517.387 | 1531.919 | 435.24 | 6.302 | 11.265 | 1.0 |
| hybrid_enriched_question | hybrid | single | single_question | enriched | enriched | 6 | 83.33% | 100.00% | 0.8611 | 0.1667 | 0.0 | 1.0 | 0.0 | 1.0 | 444.927 | 458.315 | 444.927 | 5.594 | 11.923 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | multi | multi_keyword_vector_question | enriched | raw | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 4.0 | 1.0 | 0.0 | 5.0 | 1552.728 | 1567.385 | 448.381 | 6.986 | 11.535 | 1.0 |
| hybrid_keyword_enriched_vector_raw_question | hybrid | single | single_question | enriched | raw | 6 | 100.00% | 100.00% | 0.8750 | 0.1667 | 0.0 | 1.0 | 0.0 | 1.0 | 406.117 | 420.713 | 406.117 | 5.213 | 11.75 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | multi | multi_keyword_vector_question | raw | enriched | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 4.0 | 1.0 | 0.0 | 5.0 | 2402.511 | 2414.137 | 1368.115 | 6.196 | 12.313 | 1.0 |
| hybrid_keyword_raw_vector_enriched_question | hybrid | single | single_question | raw | enriched | 6 | 83.33% | 100.00% | 0.8611 | 0.1667 | 0.0 | 1.0 | 0.0 | 1.0 | 447.984 | 461.039 | 447.984 | 4.989 | 11.548 | 1.0 |
| hybrid_raw_question | hybrid | multi | multi_keyword_vector_question | raw | raw | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 4.0 | 1.0 | 0.0 | 5.0 | 1512.354 | 1526.485 | 408.007 | 7.029 | 12.312 | 1.0 |
| hybrid_raw_question | hybrid | single | single_question | raw | raw | 6 | 100.00% | 100.00% | 0.8750 | 0.1667 | 0.0 | 1.0 | 0.0 | 1.0 | 418.31 | 432.305 | 418.31 | 5.042 | 12.011 | 1.0 |
| keyword_enriched | keyword | multi | multi_keyword_vector_question | enriched | none | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 4.0 | 0.0 | 0.0 | 4.0 | 1104.347 | 1109.675 | 0.0 | 6.082 | 0.0 | None |
| keyword_enriched | keyword | single | single_question | enriched | none | 6 | 83.33% | 100.00% | 0.8333 | 0.1667 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 4.138 | 0.0 | 4.08 | 0.0 | None |
| keyword_raw | keyword | multi | multi_keyword_vector_question | raw | none | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 4.0 | 0.0 | 0.0 | 4.0 | 1104.347 | 1113.346 | 0.0 | 8.894 | 0.0 | None |
| keyword_raw | keyword | single | single_question | raw | none | 6 | 83.33% | 100.00% | 0.7500 | 0.1667 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 10.749 | 0.0 | 9.867 | 0.0 | None |
| vector_enriched | vector | multi | single_question | none | enriched | 6 | 100.00% | 100.00% | 0.7778 | 0.1389 | 0.0 | 1.0 | 0.0 | 1.0 | 416.455 | 428.948 | 416.455 | 0.0 | 13.525 | 1.0 |
| vector_enriched | vector | single | single_question | none | enriched | 6 | 100.00% | 100.00% | 0.7778 | 0.1389 | 0.0 | 1.0 | 0.0 | 1.0 | 464.69 | 473.819 | 464.69 | 0.0 | 12.643 | 1.0 |
| vector_raw | vector | multi | single_question | none | raw | 6 | 100.00% | 100.00% | 1.0000 | 0.1667 | 0.0 | 1.0 | 0.0 | 1.0 | 415.052 | 421.749 | 415.052 | 0.0 | 13.141 | 1.0 |
| vector_raw | vector | single | single_question | none | raw | 6 | 100.00% | 100.00% | 1.0000 | 0.1667 | 0.0 | 1.0 | 0.0 | 1.0 | 444.672 | 453.816 | 444.672 | 0.0 | 12.485 | 1.0 |

## Notes

- Main hybrid policy uses planner expressions for keyword search and embeds the original question once for vector search.
- `multi_keyword_vector_expression_each` embeds every planner expression and is diagnostic/stress only.
- Planner warmup is reported in `prep_check.json` and excluded from per-case planner latency.
- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.
- `vector_recall_ms` excludes `query_embedding_ms`; query embedding is reported separately.
- Runs below 100 cases are smoke/directional, not final decision support.
