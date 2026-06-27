# Corrected Search Benchmark Verification - Spider 40 / 5 DBs

Run status: completed.

Scope: 40 Spider dev cases across 5 DBs (`concert_singer`, `pets_1`, `car_1`, `flight_2`, `employee_hire_evaluation`), 800 case rows, 20 matrix cells. This is directional evidence only because it is below 100 cases.

## Methodology Status

- Main online vector policy is question-only:
  - vector search embeds the original user question once.
  - planner expressions are not embedded for the main vector/hybrid policy.
- Multi-query planner output is still used where it belongs:
  - keyword multi search consumes the 4 planner expressions.
  - hybrid main policy combines keyword-expression recall with one vector-question recall.
- `multi_keyword_vector_expression_each` is retained only as diagnostic/stress evidence.
- `vector_recall_ms` excludes `query_embedding_ms`.
- `modeled_online_ms` includes planner time for planner-based policies and does not multiply calls beyond the selected online policy.

## Corpus Prep Check

| DB | profile | docs | AI docs | embeddings | docs=embeddings |
|---|---|---:|---:|---:|---|
| concert_singer | raw | 25 | 0 | 25 | true |
| pets_1 | raw | 17 | 0 | 17 | true |
| car_1 | raw | 29 | 0 | 29 | true |
| flight_2 | raw | 16 | 0 | 16 | true |
| employee_hire_evaluation | raw | 21 | 0 | 21 | true |
| concert_singer | enriched | 25 | 25 | 25 | true |
| pets_1 | enriched | 17 | 17 | 17 | true |
| car_1 | enriched | 29 | 29 | 29 | true |
| flight_2 | enriched | 16 | 16 | 16 | true |
| employee_hire_evaluation | enriched | 21 | 21 | 21 | true |

## Acceptance Criteria Check

For `hybrid_keyword_enriched_vector_raw_question` in multi mode:

| Requirement | Observed | Result |
|---|---|---|
| keyword datasource must be enriched | `keyword_corpus_profile=enriched` | pass |
| vector datasource must be raw | `vector_corpus_profile=raw` | pass |
| vector query must be original question only | sample `vector_expressions=["How many singers do we have?"]` | pass |
| vector expression count must be 1 | all rows `vector_expression_count=1` | pass |
| question embedding call count must be 1 | all rows `question_embedding_call_count=1` | pass |
| expression embedding call count must be 0 | all rows `expression_embedding_call_count=0` | pass |
| DB search calls must reflect 4 keyword + 1 vector | all rows `db_search_call_count=5` | pass |

For expression-each diagnostic variants:

| Requirement | Observed | Result |
|---|---|---|
| clearly labeled diagnostic/stress only | `contrast_report.md` has a separate diagnostic section | pass |
| excluded from main recommendation table | diagnostic names absent before diagnostic section | pass |
| expression embedding visible | diagnostic multi rows have avg `expression_embedding_call_count=4.0` | pass |

## Main Directional Results

Multi-mode main candidates:

| variant | keyword corpus | vector corpus | table@5 | column@10 | mrr_table | mrr_column | q embed calls | expr embed calls | measured provider p95 | modeled online p95 | query embed p95 | vector recall p95 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| keyword_raw | raw | none | 90.00% | 70.00% | 0.9542 | 0.3583 | 0.0 | 0.0 | 1123.55 | 1129.958 | 0.0 | 0.0 |
| keyword_enriched | enriched | none | 100.00% | 75.00% | 0.9542 | 0.3333 | 0.0 | 0.0 | 1123.55 | 1130.217 | 0.0 | 0.0 |
| vector_raw | none | raw | 95.00% | 75.00% | 0.9458 | 0.4917 | 1.0 | 0.0 | 420.82 | 429.318 | 420.82 | 12.53 |
| vector_enriched | none | enriched | 100.00% | 75.00% | 0.9542 | 0.4787 | 1.0 | 0.0 | 417.112 | 425.215 | 417.112 | 13.344 |
| hybrid_raw_question | raw | raw | 95.00% | 72.50% | 0.9542 | 0.3550 | 1.0 | 0.0 | 1540.93 | 1556.432 | 437.118 | 10.96 |
| hybrid_keyword_enriched_vector_raw_question | enriched | raw | 100.00% | 75.00% | 0.9542 | 0.3404 | 1.0 | 0.0 | 1503.963 | 1527.468 | 448.831 | 11.627 |
| hybrid_keyword_raw_vector_enriched_question | raw | enriched | 95.00% | 72.50% | 0.9542 | 0.3583 | 1.0 | 0.0 | 1519.548 | 1535.162 | 418.873 | 11.791 |
| hybrid_enriched_question | enriched | enriched | 100.00% | 72.50% | 0.9542 | 0.3396 | 1.0 | 0.0 | 1565.844 | 1581.571 | 420.409 | 11.412 |

Diagnostic/stress comparison:

| diagnostic variant | keyword corpus | vector corpus | table@5 | column@10 | expr embed calls | measured provider p95 | modeled online p95 | query embed p95 | vector recall p95 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| hybrid_keyword_enriched_vector_raw_expression_each | enriched | raw | 100.00% | 70.00% | 4.0 | 2760.706 | 2811.511 | 1663.517 | 43.757 |
| hybrid_enriched_expression_each | enriched | enriched | 100.00% | 62.50% | 4.0 | 2688.391 | 2733.144 | 1694.971 | 45.155 |

## Directional Reading

The corrected design shows that the main mixed hybrid policy (`keyword_enriched + vector_raw + question-only vector`) is much closer to a realistic online agent: one planner call, four keyword searches, one question embedding, and one vector search. Its table recall reaches 100% in this sample, while avoiding the inflated vector embedding cost of expression-each.

The expression-each diagnostic rows are useful as a warning: they do not improve table recall in this run, reduce column recall, and raise p95 query embedding from roughly 0.42-0.45s to roughly 1.66-1.69s. They should stay out of recommendation tables.

Do not treat this as final ranking. The next decision-support stage needs at least 100 cases and 10+ DBs.

## Artifacts

- `prep_check.json`
- `search_plans.json`
- `contrast_cases.csv`
- `contrast_cases.jsonl`
- `contrast_summary.json`
- `contrast_report.md`
- `progress_events.jsonl`
