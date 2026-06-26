# Spider Retrieval A/B/n Report

Variants: keyword, vector, hybrid

| variant | table_recall@5 | column_recall@10 | task_solve_rate | query_exec_success | p95_latency | p95_retrieval_ms | p95_embedding_ms | avg_embedding_ms | safety_violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyword | 95.0% | 95.0% | 0.0% | 0.0% | 12 | 12.4 |  |  | 0 |
| vector | 95.0% | 100.0% | 0.0% | 0.0% | 3567 | 3567.8 | 10.0 | 8.0 | 0 |
| hybrid | 100.0% | 100.0% | 0.0% | 0.0% | 1920 | 1920.3 | 8.2 | 5.9 | 0 |

## Failure breakdown

| variant | failure_class | count | rate |
| --- | --- | ---: | ---: |
| keyword | none | 19 | 95.0% |
| keyword | retrieval_miss | 1 | 5.0% |
| vector | none | 19 | 95.0% |
| vector | retrieval_miss | 1 | 5.0% |
| hybrid | none | 20 | 100.0% |
