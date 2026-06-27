# Spider Retrieval Profile Contrast Report

| variant | retriever | query_mode | cases | table@5 | column@10 | mrr_table | mrr_column | planner p50/p90/p95/max | query embedding p95 | retrieval p50/p90/p95/max | e2e p50/p90/p95/max | vector_available |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hybrid_enriched | hybrid | multi | 6 | 100.00% | 100.00% | 1.0000 | 0.1667 | 824.721/881.51/881.51/881.51 | 1851.78 | 1850.99/1911.04/1911.04/1911.04 | 2624.02/2792.55/2792.55/2792.55 | 1.0 |
| hybrid_enriched | hybrid | single | 6 | 83.33% | 100.00% | 0.8611 | 0.1667 | 0.0/0.0/0.0/0.0 | 454.464 | 458.255/468.737/468.737/468.737 | 458.255/468.737/468.737/468.737 | 1.0 |
| hybrid_raw | hybrid | multi | 6 | 100.00% | 100.00% | 1.0000 | 0.1667 | 824.721/881.51/881.51/881.51 | 1905.557 | 1931.784/1970.421/1970.421/1970.421 | 2741.084/2837.265/2837.265/2837.265 | 1.0 |
| hybrid_raw | hybrid | single | 6 | 100.00% | 100.00% | 0.8750 | 0.1667 | 0.0/0.0/0.0/0.0 | 546.681 | 479.939/569.323/569.323/569.323 | 479.939/569.323/569.323/569.323 | 1.0 |
| keyword_enriched | keyword | multi | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 824.721/881.51/881.51/881.51 | 0.0 | 9.5/12.116/12.116/12.116 | 836.186/887.967/887.967/887.967 | None |
| keyword_enriched | keyword | single | 6 | 83.33% | 100.00% | 0.8333 | 0.1667 | 0.0/0.0/0.0/0.0 | 0.0 | 6.005/10.072/10.072/10.072 | 6.005/10.072/10.072/10.072 | None |
| keyword_raw | keyword | multi | 6 | 100.00% | 100.00% | 1.0000 | 0.1389 | 824.721/881.51/881.51/881.51 | 0.0 | 8.788/14.379/14.379/14.379 | 832.343/895.889/895.889/895.889 | None |
| keyword_raw | keyword | single | 6 | 83.33% | 100.00% | 0.7500 | 0.1667 | 0.0/0.0/0.0/0.0 | 0.0 | 9.598/15.851/15.851/15.851 | 9.598/15.851/15.851/15.851 | None |
| vector_enriched | vector | multi | 6 | 100.00% | 100.00% | 0.8056 | 0.1667 | 824.721/881.51/881.51/881.51 | 2848.149 | 1932.229/2905.639/2905.639/2905.639 | 2766.806/3655.616/3655.616/3655.616 | 1.0 |
| vector_enriched | vector | single | 6 | 100.00% | 100.00% | 0.7778 | 0.1389 | 0.0/0.0/0.0/0.0 | 2020.285 | 554.43/2030.61/2030.61/2030.61 | 554.43/2030.61/2030.61/2030.61 | 1.0 |
| vector_raw | vector | multi | 6 | 100.00% | 100.00% | 1.0000 | 0.2500 | 824.721/881.51/881.51/881.51 | 1882.555 | 1890.454/1949.692/1949.692/1949.692 | 2711.685/2743.732/2743.732/2743.732 | 1.0 |
| vector_raw | vector | single | 6 | 100.00% | 100.00% | 1.0000 | 0.1667 | 0.0/0.0/0.0/0.0 | 479.224 | 471.45/488.246/488.246/488.246 | 471.45/488.246/488.246/488.246 | 1.0 |

## Notes

- `multi` mode uses pre-generated search expressions; planner warmup is reported in `prep_check.json` and excluded from per-case planner latency.
- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.
- `query embedding` is online query-vectorization time and remains visible separately from retrieval and planner time.
