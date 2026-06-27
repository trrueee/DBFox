# Corrected Search Benchmark Verification - Spider 24 / 3 DBs

Run status: completed.

Scope: 24 Spider dev cases across 3 DBs (`concert_singer`, `pets_1`, `car_1`), 480 case rows, 20 matrix cells. This is a small directional run, not final decision support.

## What This Run Verifies

- Raw and enriched schema corpora coexist per DB.
- Raw and enriched embeddings coexist per DB.
- Vector query timing is split from vector DB search timing:
  - `query_embedding_ms` / `question_embedding_ms` report provider embedding time.
  - `vector_recall_ms` excludes query embedding time.
- The main hybrid online policy is `multi_keyword_vector_question`:
  - planner expressions feed keyword search.
  - the original user question feeds vector search once.
- The old `multi_keyword_vector_expression_each` behavior is present only as diagnostic/stress evidence.
- Diagnostic/stress variants are excluded from the main recommendation table.

## Corpus Prep Check

| DB | profile | docs | AI docs | embeddings | docs=embeddings |
|---|---|---:|---:|---:|---|
| concert_singer | raw | 25 | 0 | 25 | true |
| pets_1 | raw | 17 | 0 | 17 | true |
| car_1 | raw | 29 | 0 | 29 | true |
| concert_singer | enriched | 25 | 25 | 25 | true |
| pets_1 | enriched | 17 | 17 | 17 | true |
| car_1 | enriched | 29 | 29 | 29 | true |

## Acceptance Criteria Check

For `hybrid_keyword_enriched_vector_raw_question` in multi mode:

| Requirement | Observed | Result |
|---|---|---|
| keyword datasource must be enriched | `keyword_corpus_profile=enriched` | pass |
| vector datasource must be raw | `vector_corpus_profile=raw` | pass |
| vector query must be original question only | sample `vector_expressions=["How many singers do we have?"]` | pass |
| vector expression count must be 1 | all rows `vector_expression_count=1` | pass |
| expression embedding call count must be 0 | all rows `expression_embedding_call_count=0` | pass |
| question embedding call count must be 1 | all rows `question_embedding_call_count=1` | pass |
| DB search call count must be explicit | all rows `db_search_call_count=5` | pass |

For expression-each diagnostic variants:

| Requirement | Observed | Result |
|---|---|---|
| clearly labeled diagnostic/stress only | report has `Diagnostic / Stress Variants` section | pass |
| excluded from main recommendation table | diagnostic variant names are absent before diagnostic section | pass |
| expression embeddings are visible | avg `expression_embedding_call_count=4.0` | pass |

## Key Result Snapshot

| variant | query mode | policy | keyword corpus | vector corpus | table@5 | column@10 | q embed p95 | vector recall p95 | measured provider p95 | modeled online p95 |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| keyword_enriched | multi | multi_keyword_vector_question | enriched | none | 100.00% | 91.67% | 0.0 | 0.0 | 1233.758 | 1242.423 |
| vector_raw | multi | single_question | none | raw | 91.67% | 91.67% | 441.751 | 13.047 | 441.751 | 448.771 |
| hybrid_keyword_enriched_vector_raw_question | multi | multi_keyword_vector_question | enriched | raw | 100.00% | 91.67% | 483.66 | 12.609 | 1619.833 | 1638.306 |
| hybrid_enriched_question | multi | multi_keyword_vector_question | enriched | enriched | 100.00% | 91.67% | 458.226 | 13.884 | 1624.514 | 1647.08 |
| hybrid_keyword_enriched_vector_raw_expression_each | multi | multi_keyword_vector_expression_each | enriched | raw | 100.00% | 83.33% | 1670.683 | 44.362 | 2773.764 | 2831.807 |

## Interpretation

This run confirms the corrected comparison design is wired correctly. The important methodological result is not just the quality numbers; it is that the main hybrid policy no longer charges vector retrieval for planner-expression embeddings. The diagnostic expression-each rows show why the old policy was misleading: they embed 4 planner expressions per case and therefore inflate `query_embedding_ms` and provider time.

Because this run has only 24 cases, treat quality deltas as directional. It is valid for methodology verification and obvious-regression detection, not final release ranking.

## Artifacts

- `prep_check.json`: corpus, datasource, embedding, planner warmup, and selected case metadata.
- `contrast_cases.csv`: per-case quality, latency, corpus profile, query policy, and call-count fields.
- `contrast_summary.json`: grouped metrics by variant/retriever/query policy.
- `contrast_report.md`: main recommendation table plus diagnostic/stress table.
- `progress_events.jsonl`: streamed run progress and per-case timing events.
