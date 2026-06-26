# Spider retrieval evaluation method

## Background

This document records the current Spider retrieval evaluation approach for DBFox. It covers the lessons learned from the recent compatibility and agent-design debugging round, especially around environment context, tool contracts, schema search, vector embeddings, and the evaluation chain.

The current target is not only to compare keyword/vector/hybrid retrieval, but to test a more realistic agent retrieval path:

1. The model plans multiple search expressions from the user question.
2. The same planned expressions are reused across retrieval variants.
3. Each variant performs schema retrieval.
4. Multi-query results are fused.
5. Recall is calculated from the fused result.

This is different from the earlier bare retrieval test where `case.question` was passed directly into `db.search`. The bare form is useful as a low-level smoke test, but it does not represent the real agent path.

## Key Handling

No full provider API key should be written into source files, docs, reports, SQLite artifacts, or git history.

The key used in this run was provided locally by the user and injected through environment variables only. The document records the required variables and provider configuration, not the secret value.

Recommended variables:

```powershell
$env:DBFOX_RETRIEVAL_PLANNER_API_KEY = "<local-secret>"
$env:DBFOX_RETRIEVAL_PLANNER_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DBFOX_RETRIEVAL_PLANNER_MODEL = "qwen-plus"

$env:DBFOX_EMBEDDING_API_KEY = "<local-secret>"
$env:DBFOX_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DBFOX_EMBEDDING_MODEL = "text-embedding-v4"
$env:DBFOX_EMBEDDING_DIMENSION = "1024"
```

Supported fallback variables in code:

- Planner key: `DBFOX_RETRIEVAL_PLANNER_API_KEY`, `OPENAI_API_KEY`, `QWEN_API_KEY`, `DBFOX_EMBEDDING_API_KEY`, `DASHSCOPE_API_KEY`
- Planner base URL: `DBFOX_RETRIEVAL_PLANNER_BASE_URL`, `QWEN_API_BASE`, `OPENAI_API_BASE`, `OPENAI_BASE_URL`, `DBFOX_EMBEDDING_BASE_URL`
- Planner model: `DBFOX_RETRIEVAL_PLANNER_MODEL`, `QWEN_MODEL_NAME`, `OPENAI_MODEL_NAME`
- Embedding key: `DBFOX_EMBEDDING_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, `QWEN_API_KEY`
- Embedding base URL: `DBFOX_EMBEDDING_BASE_URL`, `OPENAI_BASE_URL`, `OPENAI_API_BASE`

Security checks used after the run:

```powershell
rg -n "sk-<secret>|<secret-body>" engine reports\retrieval_ab_ai_assisted_spider50_real_provider reports\retrieval_ab_ai_assisted_real_provider
```

Expected result: no matches.

## Framework

The retrieval eval is organized around a small A/B/n framework:

- Cases are loaded from Spider-style JSON.
- Required tables and columns are derived from gold SQL.
- Datasources are prepared from Spider SQLite databases and table metadata.
- Schema search docs are generated from datasource schema.
- Vector embeddings are built for the schema docs before vector/hybrid evaluation.
- The retrieval variants are run under the same planned search expressions.
- Reports are written as summary JSON, per-case CSV, JSONL, and Markdown.

Current variants:

| variant | meaning |
|---|---|
| `keyword` | schema keyword search over generated schema docs |
| `vector` | embedding search over generated schema docs |
| `hybrid` | keyword + vector retrieval with fused ranking |

Current mode:

| mode | meaning |
|---|---|
| `retrieval-only` | direct retrieval test, usually using the raw question |
| `ai-assisted-retrieval` | LLM plans multiple search expressions, then retrieval runs over those expressions |

The current realistic mode is `ai-assisted-retrieval`.

## Code Method

Important implementation points:

- `engine/evaluation/retrieval_ab/query_planner.py`
  - Generates 2-4 compact search expressions from each case question.
  - Uses an LLM provider through local env configuration.
  - Avoids gold SQL leakage in the prompt.

- `engine/evaluation/retrieval_ab/cli.py`
  - Adds `ai-assisted-retrieval` mode.
  - Caches one search plan per case so keyword/vector/hybrid compare the same planned expressions.
  - Runs each planned expression through `db.search`.
  - Emits a synthetic `db.search.fused` event for recall evaluation.

- `engine/evaluation/retrieval_ab/runner.py`
  - Collects fused `db.search.fused` results first.
  - Falls back to raw `db.search` events when no fused event exists.
  - Carries `search_expressions` into metrics and reports.

- `engine/evaluation/retrieval_ab/metrics.py`
  - Treats both `retrieval-only` and `ai-assisted-retrieval` as retrieval evaluation modes.
  - Calculates table and column recall from retrieved schema hits.

- `engine/evaluation/retrieval_ab/report.py`
  - Adds `search_expressions` and `db_search_call_count` to per-case report rows.

- `engine/tools/db/embedding.py`
  - Resolves embedding provider configuration.
  - Builds embeddings with the DashScope OpenAI-compatible endpoint by default.

- `engine/tools/db/search.py`
  - Supports keyword, vector, and hybrid schema search.
  - Reports vector availability and embedding build timing.

- `reports/retrieval_ab_ai_assisted_real_provider/run_ai_assisted_real_provider.py`
  - Local report runner used for real-provider smoke/regression runs.
  - Accepts dataset path, case limit, report directory, and top K through env vars.

Related SQL tool-contract fix:

- `engine/tools/dbfox_tools.py`
- `engine/tools/db/sql_execution.py`
- `engine/policy/gate.py`

The corrected contract is:

```text
sql.validate(sql)
  -> writes state.safety.safe_sql

sql.execute_readonly(question?)
  -> does not accept model SQL
  -> executes only state.safety.safe_sql
  -> records ignored_model_sql if the model still tried to pass SQL
```

This avoids the previous mismatch where the model could slightly rewrite SQL between validation and execution, causing `safe_sql mismatch`.

## Data

Local Spider root found on D drive:

```text
D:\DBFoxData\spider\spider_data
```

Primary files:

```text
D:\DBFoxData\spider\spider_data\dev.json
D:\DBFoxData\spider\spider_data\tables.json
D:\DBFoxData\spider\spider_data\database\
D:\DBFoxData\spider\spider_data\test_database\
```

The full Spider dev set has 1034 rows. The first larger real-provider run used the first 50 dev cases. This slice covers only 2 databases:

- `concert_singer`
- `pets_1`

This is larger than the tiny fixture but should not be treated as a final global Spider score because the first 50 rows are not database-diverse.

Additional local test fixture:

```text
engine/tests/fixtures/spider_tiny/dev_expanded.json
```

That fixture contains 20 small cases and is useful for fast regression tests. It should not be used as proof of real Spider performance.

## Preflight Checks

Before running vector/hybrid retrieval, verify schema docs and embeddings:

| db_id | schema tables | schema columns | schema search docs | embedding rows | stale embeddings | docs equal embeddings |
|---|---:|---:|---:|---:|---:|---|
| `concert_singer` | 4 | 21 | 25 | 25 | 0 | true |
| `pets_1` | 3 | 14 | 17 | 17 | 0 | true |

Vector smoke checks from the Spider50 run:

| db_id | mode | vector_available | total_matches |
|---|---|---:|---:|
| `concert_singer` | vector | true | 20 |
| `concert_singer` | hybrid | true | 20 |
| `pets_1` | vector | true | 17 |
| `pets_1` | hybrid | true | 18 |

This confirms that the Spider50 vector/hybrid run used real provider embeddings instead of the deterministic local stub.

## Reproduction Command

Example PowerShell command for the Spider50 real-provider run:

```powershell
$env:DBFOX_RETRIEVAL_PLANNER_API_KEY = "<local-secret>"
$env:DBFOX_RETRIEVAL_PLANNER_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DBFOX_RETRIEVAL_PLANNER_MODEL = "qwen-plus"

$env:DBFOX_EMBEDDING_API_KEY = "<local-secret>"
$env:DBFOX_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DBFOX_EMBEDDING_MODEL = "text-embedding-v4"
$env:DBFOX_EMBEDDING_DIMENSION = "1024"

$env:DBFOX_EVAL_CASES = "D:\DBFoxData\spider\spider_data\dev.json"
$env:DBFOX_EVAL_CASE_LIMIT = "50"
$env:DBFOX_RETRIEVAL_TOP_K = "20"
$env:DBFOX_EVAL_REPORT_DIR = "reports\retrieval_ab_ai_assisted_spider50_real_provider"

python reports\retrieval_ab_ai_assisted_real_provider\run_ai_assisted_real_provider.py
```

Expected artifacts:

```text
reports\retrieval_ab_ai_assisted_spider50_real_provider\prep_check.json
reports\retrieval_ab_ai_assisted_spider50_real_provider\search_plans.json
reports\retrieval_ab_ai_assisted_spider50_real_provider\metadata.sqlite
reports\retrieval_ab_ai_assisted_spider50_real_provider\spider_keyword_vector_hybrid_summary.json
reports\retrieval_ab_ai_assisted_spider50_real_provider\spider_keyword_vector_hybrid_cases.csv
reports\retrieval_ab_ai_assisted_spider50_real_provider\spider_keyword_vector_hybrid_cases.jsonl
reports\retrieval_ab_ai_assisted_spider50_real_provider\spider_keyword_vector_hybrid_report.md
```

## Results

Spider50 real-provider run:

| variant | cases | table_recall@5 | column_recall@10 | vector_available | db.search calls | retrieval_miss | p95 retrieval latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| `keyword` | 50 | 100.0% | 74.0% | n/a | 200 | 13 | 15.632 ms |
| `vector` | 50 | 90.0% | 72.0% | 100.0% | 200 | 15 | 2330.925 ms |
| `hybrid` | 50 | 92.0% | 72.0% | 100.0% | 200 | 15 | 3675.797 ms |

Miss shape:

| variant | table hit | column hit | count |
|---|---:|---:|---:|
| `keyword` | true | true | 37 |
| `keyword` | true | false | 13 |
| `vector` | true | true | 35 |
| `vector` | true | false | 10 |
| `vector` | false | true | 1 |
| `vector` | false | false | 4 |
| `hybrid` | true | true | 35 |
| `hybrid` | true | false | 11 |
| `hybrid` | false | true | 1 |
| `hybrid` | false | false | 3 |

Earlier expanded tiny 20-case run:

| variant | cases | table_recall@5 | column_recall@10 | vector_available | retrieval_miss |
|---|---:|---:|---:|---:|---:|
| `keyword` | 20 | 95.0% | 95.0% | n/a | 1 |
| `vector` | 20 | 95.0% | 100.0% | 100.0% | 1 |
| `hybrid` | 20 | 100.0% | 100.0% | 100.0% | 0 |

The tiny result looked good, but the Spider50 result shows that the tiny fixture was too easy and not representative enough.

## Interpretation

Main conclusions:

- The vector/hybrid environment is working.
- Schema docs exist and match embedding rows.
- Real provider calls are being used.
- The remaining weakness is retrieval quality, not provider availability.
- `keyword` outperformed `vector` and `hybrid` on the Spider50 slice.
- `hybrid` does not yet reliably improve over `keyword`; vector noise can drag fused rankings down.
- Column recall is weaker than table recall across all variants.
- Misses are concentrated around `concert_singer`, especially `stadium`, `concert`, joins, and aggregation-heavy questions.

The useful diagnostic split is:

```text
environment problem?
  -> check provider key, base URL, embedding row count, vector_available

schema doc problem?
  -> check whether table/column/foreign-key text is actually searchable

query planning problem?
  -> inspect search_plans.json

ranking/fusion problem?
  -> compare keyword/vector/hybrid raw hits and db.search.fused output

eval problem?
  -> verify expected tables/columns extracted from gold SQL
```

## Lessons Learned

1. Bare `db.search(question)` is not enough.

   It can validate the low-level search tool, but it does not reflect how the agent searches. The realistic path needs AI-planned multi-query retrieval.

2. Use the same planned expressions for all variants.

   If keyword/vector/hybrid each get independently generated queries, the result mixes retrieval quality with planner randomness. Cache by case id.

3. Prep must be explicit.

   For vector/hybrid, do not trust a run unless `schema_search_doc_count == embedding_row_count`, stale embeddings are zero, and `vector_available` is true.

4. Tiny fixtures are good for regression, not ranking conclusions.

   The 20-case tiny fixture made hybrid look perfect. Spider50 immediately exposed vector/hybrid ranking and fusion issues.

5. Report fused results, but keep raw events.

   The fused event is the right target for recall metrics, while raw `db.search` events are needed to debug which query or retrieval leg caused the miss.

6. SQL execution should consume validated state, not model-resubmitted SQL.

   The corrected `sql.validate -> sql.execute_readonly` contract removes a class of false blocks caused by harmless SQL formatting drift or model rewrites.

7. Do not silently ignore model contract violations.

   If the model still sends SQL to `sql.execute_readonly`, execution should ignore it but telemetry should record `ignored_model_sql`.

## Verification

Related tests:

```powershell
$env:TEMP = "D:\tmp_codex_pytest"
$env:TMP = "D:\tmp_codex_pytest"
$env:PYTHONDONTWRITEBYTECODE = "1"

python -m pytest -p no:cacheprovider --basetemp D:\tmp_codex_pytest `
  engine/tests/test_retrieval_ab_config_report_runner.py `
  engine/tests/test_retrieval_ab_metrics.py `
  engine/tests/test_retrieval_ab_variants.py `
  engine/tests/test_schema_vector_search.py `
  -q
```

Result:

```text
35 passed, 10 warnings
```

The normal pytest cache path could not be used during this run because the C drive reported 0 bytes free. Using D drive temp storage and disabling pytest cache writing allowed the verification to complete.

## Next Steps

Recommended next evaluation steps:

1. Build a more diverse Spider sample rather than using the first N rows.
2. Run at least 100-200 cases across many DBs before drawing ranking conclusions.
3. Add report fields for raw top hits per planned expression.
4. Improve schema docs with foreign-key relationships and table role summaries.
5. Tune hybrid fusion so strong keyword matches are not demoted by noisy vector hits.
6. Add planner constraints to include exact schema-like identifiers when useful.
7. Add per-case diagnostics for missing expected table vs missing expected column.
8. Keep key scan and prep checks as mandatory before accepting a real-provider report.
