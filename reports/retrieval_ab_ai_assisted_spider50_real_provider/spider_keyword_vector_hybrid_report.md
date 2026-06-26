# Spider Retrieval A/B/n Report

Variants: keyword, vector, hybrid

| variant | table_recall@5 | column_recall@10 | task_solve_rate | query_exec_success | p95_latency | p95_retrieval_ms | p95_embedding_ms | avg_embedding_ms | safety_violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyword | 100.0% | 74.0% | 0.0% | 0.0% | 16 | 15.6 |  |  | 0 |
| vector | 90.0% | 72.0% | 0.0% | 0.0% | 2329 | 2330.9 | 12.5 | 9.0 | 0 |
| hybrid | 92.0% | 72.0% | 0.0% | 0.0% | 3674 | 3675.8 | 18.9 | 11.9 | 0 |

## Failure breakdown

| variant | failure_class | count | rate |
| --- | --- | ---: | ---: |
| keyword | none | 37 | 74.0% |
| keyword | retrieval_miss | 13 | 26.0% |
| vector | none | 35 | 70.0% |
| vector | retrieval_miss | 15 | 30.0% |
| hybrid | none | 35 | 70.0% |
| hybrid | retrieval_miss | 15 | 30.0% |
