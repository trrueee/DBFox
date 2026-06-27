# Spider Retrieval A/B/n Report

Variants: keyword, vector, hybrid

| variant | table_recall@5 | column_recall@10 | task_solve_rate | query_exec_success | p95_latency | p95_retrieval_ms | p95_embedding_ms | avg_embedding_ms | safety_violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyword | 94.1% | 69.2% | 0.0% | 0.0% | 29 | 27.8 |  |  | 0 |
| vector | 92.4% | 68.9% | 0.0% | 0.0% | 3015 | 3018.7 | 34.0 | 18.3 | 0 |
| hybrid | 94.8% | 70.2% | 0.0% | 0.0% | 3168 | 3171.8 | 36.3 | 19.6 | 0 |

## Failure breakdown

| variant | failure_class | count | rate |
| --- | --- | ---: | ---: |
| keyword | none | 198 | 68.5% |
| keyword | retrieval_miss | 91 | 31.5% |
| vector | none | 196 | 67.8% |
| vector | retrieval_miss | 93 | 32.2% |
| hybrid | none | 200 | 69.2% |
| hybrid | retrieval_miss | 89 | 30.8% |
