# Retrieval A/B Observability Design

## Goal

Stabilize the Spider retrieval A/B/n evaluation chain before comparing retrieval strategies. The first implementation slice should make every case observable and attributable, even when the Agent fails, loops, times out, calls an unknown tool, or produces SQL that cannot execute on SQLite.

The output of this work is not a better Agent and not a better retriever. The output is a trustworthy evaluation harness that can answer where a case failed: retrieval, Agent behavior, SQL compatibility, tool/policy handling, or infrastructure.

## Background

The previous Spider eval run did not produce a reliable comparison between `keyword`, `vector`, and `hybrid`. The logs showed PolicyGate blocks, loop prevention, recursion-limit failures, SQLite/Spider SQL compatibility errors, unknown tool calls, model-service timeouts, and missing or incomplete reports. Those failures make task pass/fail unsuitable as a retrieval quality signal.

Current `engine.evaluation.retrieval_ab` code already has useful pieces:

- `config.py` loads benchmark, variants, model, case path, and report settings.
- `spider_fixture.py` derives expected tables and columns from Spider gold SQL.
- `runner.py` extracts `db.search` hits and trace metrics from Agent events.
- `metrics.py` computes table recall, column recall, SQL table/column usage, and task solved.
- `report.py` writes summary JSON, cases CSV, and markdown summary.
- `cli.py` can run dry reports or live Agent evaluation.

The gap is that failures are still too coarse. A single `failure_reason` string does not consistently distinguish retrieval misses from Agent/tool/SQL/infra failures, and reports are written at the end of the run instead of preserving partial case output during long or unstable runs.

## Scope

This phase focuses on the evaluation chain:

- Add structured failure classification for case-level results.
- Add durable per-case output suitable for partial results.
- Add a retrieval-only mode for isolating schema recall from live Agent execution.
- Add a smoke-oriented execution shape for small, cheap validation runs.
- Expand reports so strategy comparison and failure diagnosis use the same case-level data.

This phase intentionally does not change:

- Agent prompts, planning, loop recovery, or graph recursion behavior.
- PolicyGate behavior.
- SQL builder identifier rules.
- SQLite dialect compatibility.
- Embedding model behavior or ranking formulas.

Those areas should be addressed in later phases after this harness can identify which class of failure dominates.

## Failure Taxonomy

Each evaluated case should have a normalized `failure_class` in addition to the existing human-readable `failure_reason`.

Initial classes:

- `none`: the case is solved.
- `retrieval_miss`: expected tables or columns are absent from retrieval output.
- `agent_no_sql`: live Agent completed without a final SQL query.
- `agent_loop_or_recursion`: logs or errors indicate repeated tool calls, loop prevention, or graph recursion limit.
- `policy_gate_block`: PolicyGate blocked a known tool call.
- `unknown_tool`: PolicyGate or tool runtime reported an unknown tool such as `environment_get_profile`.
- `sql_compatibility`: SQLite/Spider incompatibility, including unsupported operators like `ILIKE`, schema parse errors, invalid identifiers, ambiguous columns, or preview failures caused by Spider-style names.
- `query_execution_failed`: SQL was generated but did not execute successfully for a reason not classified as SQL compatibility.
- `model_or_infra_error`: model service, network, timeout, or upstream provider failures.
- `unknown`: the case failed and available evidence does not fit a known class.

Classification should use existing evidence first: Agent events, extracted SQL, execution comparison error, artifact error text, safety counts, and retrieval metrics. The classifier should not hide raw reasons; it should preserve the original error text for inspection.

## Case-Level Output

Every case row should include enough fields to answer both retrieval and live execution questions:

- `case_id`, `db_id`, `variant`, `question`
- `expected_tables`, `expected_columns`
- `retrieved_tables_top5`, `retrieved_columns_top10`
- `actual_sql`
- `used_tables`, `used_columns`
- `table_recall_at_5`, `column_recall_at_10`
- `query_generated`, `query_execution_success`, `task_solved`
- `latency_ms`, `retrieval_latency_ms`, `embedding_build_time_ms`
- `step_count`, `tool_call_count`, `db_search_call_count`, `schema_observe_count`
- `failure_class`, `failure_reason`

The CSV should remain useful for spreadsheet inspection. A JSONL case stream should be added for durable partial output during large runs. Each case should be appended as soon as it is evaluated so interrupted runs still leave analyzable data.

## Modes

The CLI should support two explicit modes:

- `retrieval-only`: run schema retrieval for each case and compute expected-vs-retrieved metrics without invoking the live Agent.
- `live`: run the current Agent-backed flow and compute both retrieval and task execution metrics.

Dry run without `--execute` should remain cheap and deterministic. The new retrieval-only path should be the recommended first stage for full Spider runs because it answers whether tables and columns are being recalled before spending model calls on Agent execution.

The implementation should preserve current defaults where practical so existing tests and scripts do not unexpectedly start making live model calls.

## Reporting

Reports should have two layers:

1. Case artifacts for diagnosis:
   - CSV for spreadsheet analysis.
   - JSONL for partial and machine-readable case data.

2. Variant summaries for comparison:
   - Existing recall and solve-rate metrics.
   - Counts and rates by `failure_class`.
   - Retrieval latency and embedding build timing.
   - Tool and step counts for spotting loop-heavy runs.

Markdown should include a compact failure breakdown table per variant. Summary JSON should include enough structured counts to support later dashboards or notebooks.

## Data Flow

For `retrieval-only`:

1. Load Spider cases.
2. Register or reuse the Spider datasource when needed for search.
3. Run the configured retrieval variant for the case question.
4. Convert search results into `RetrievalHit` rows.
5. Evaluate table and column recall.
6. Classify retrieval-only failure as `retrieval_miss` or `none`.
7. Append case JSONL immediately.
8. Write final CSV, summary JSON, and markdown.

For `live`:

1. Load Spider cases and examples.
2. Set `DBFOX_SCHEMA_RETRIEVAL_MODE` for the variant.
3. Prewarm embeddings for vector or hybrid when needed.
4. Run the Agent case.
5. Extract final SQL and Agent events.
6. Compare predicted SQL execution against gold SQL when execution is enabled.
7. Collect retrieval hits and trace metrics from events.
8. Classify failure using retrieval state, Agent artifacts, SQL comparison error, and raw events.
9. Append case JSONL immediately.
10. Write final CSV, summary JSON, and markdown.

## Testing

Unit tests should cover:

- Failure classification from representative error strings and event shapes.
- Case evaluation emits `failure_class` and preserves `failure_reason`.
- Reports include failure-class fields in CSV and summary JSON.
- Markdown includes failure breakdown by variant.
- JSONL writer appends one row per evaluated case.
- Retrieval-only mode can run without calling the live Agent.
- Existing dry-run behavior remains non-live.

Tests should use small fixtures and monkeypatches, not real model calls. Live Spider evaluation remains outside the default test suite.

## Acceptance Criteria

- A failed or interrupted run leaves case-level JSONL rows for completed cases.
- Case CSV includes `failure_class`, `failure_reason`, expected schema, retrieved schema, used schema, and core counters.
- Summary JSON and markdown include failure breakdown by variant.
- Retrieval-only mode can answer table and column recall without invoking the Agent.
- Existing retrieval A/B tests pass.
- No Agent, PolicyGate, SQL builder, or SQLite compatibility behavior is changed in this phase.
