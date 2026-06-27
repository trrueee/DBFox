# Spider AI Enrich Contrast Report

| schema_variant | retriever | query_mode | cases | table@5 | column@10 | mrr_table | mrr_column | planner p95 | query embedding p95 | retrieval p95 | e2e p95 | vector_available |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ai_enriched | hybrid | multi | 12 | 100.00% | 83.33% | 1.0000 | 0.3472 | 21832.129 | 1790.822 | 1844.068 | 23581.727 | 1.0 |
| ai_enriched | hybrid | single | 12 | 91.67% | 91.67% | 0.9306 | 0.3750 | 0.0 | 471.13 | 491.225 | 491.225 | 1.0 |
| ai_enriched | keyword | multi | 12 | 100.00% | 100.00% | 1.0000 | 0.2639 | 21832.129 | 0.0 | 19.021 | 21845.331 | None |
| ai_enriched | keyword | single | 12 | 91.67% | 75.00% | 0.8611 | 0.4167 | 0.0 | 0.0 | 13.356 | 13.356 | None |
| ai_enriched | vector | multi | 12 | 100.00% | 83.33% | 0.9028 | 0.3333 | 21832.129 | 1879.262 | 1920.197 | 23709.657 | 1.0 |
| ai_enriched | vector | single | 12 | 100.00% | 100.00% | 0.8889 | 0.2847 | 0.0 | 549.835 | 561.309 | 561.309 | 1.0 |
| base | hybrid | multi | 12 | 100.00% | 83.33% | 1.0000 | 0.4028 | 21832.129 | 1942.105 | 2010.606 | 23842.735 | 1.0 |
| base | hybrid | single | 12 | 100.00% | 100.00% | 0.9375 | 0.3944 | 0.0 | 526.606 | 550.072 | 550.072 | 1.0 |
| base | keyword | multi | 12 | 100.00% | 91.67% | 1.0000 | 0.2917 | 21832.129 | 0.0 | 23.152 | 21855.281 | None |
| base | keyword | single | 12 | 91.67% | 58.33% | 0.8750 | 0.4167 | 0.0 | 0.0 | 21.176 | 21.176 | None |
| base | vector | multi | 12 | 100.00% | 100.00% | 1.0000 | 0.5000 | 21832.129 | 1967.205 | 2025.698 | 23774.927 | 1.0 |
| base | vector | single | 12 | 100.00% | 100.00% | 1.0000 | 0.3472 | 0.0 | 498.558 | 514.132 | 514.132 | 1.0 |

## Notes

- `e2e p95` includes LLM query expansion for `multi` mode and retrieval-only time.
- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.
