# Search Benchmark Methodology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fair, auditable retrieval benchmark that separates corpus enrichment, planner expansion, query embedding policy, retrieval quality, and online latency.

**Architecture:** The benchmark should freeze planner outputs and embedding inputs before running retrieval variants, then evaluate retrieval methods against the same prepared artifacts. Query policy must be explicit: keyword can consume multiple planner expressions while vector can use either only the original question or every planner expression. Reports must show quality, online stage latency, offline prep latency, and provider call counts separately.

**Tech Stack:** Python, pytest, SQLAlchemy metadata DB, existing `engine.evaluation.retrieval_ab` runner modules, existing `engine.tools.db.search` keyword/vector/hybrid search, Spider fixtures.

## Global Constraints

- Do not treat the interrupted 40-case run as final evidence; it used the current `expression_each` vector policy and was stopped for methodology redesign.
- Keep API keys out of committed files. Reports may mention the env file path `C:\Users\Lenovo\.dbfox\dbfox-eval.env`, but must not include key values.
- Raw and enriched schema corpora must coexist for every selected DB before any variant runs.
- Raw and enriched schema embeddings must coexist for every selected DB before any variant runs.
- Planner warmup is recorded separately and excluded from case latency.
- Offline corpus sync, AI enrichment, and corpus embedding build are reported separately from online case latency.
- Every benchmark row must declare its query policy, keyword corpus profile, vector corpus profile, planner expression count, embedding call count, and db search call count.

---

## Current Code Facts

The current multi-query runner calls `db_search` once per planner expression:

- `engine/evaluation/retrieval_ab/cli.py::_run_ai_assisted_retrieval_case`
- Lines 203-219 compute `expressions` and call `db_search(db_session, datasource_id, expression, limit)` for each expression.
- `fuse_multi_query_search_outputs` then sums child `query_embedding_ms`, `keyword_recall_ms`, `vector_recall_ms`, `merge_ms`, and `retrieval_only_ms`.

This means current `multi` mode is:

```text
planner(question) -> expression_1..expression_n
for every expression:
  db.search(expression)
fuse all db.search outputs
```

For vector and hybrid, that implies:

```text
query_embedding_ms = sum(embedding(expression_i))
```

That is a valid stress/diagnostic policy, but it is not the only realistic agent design. The likely online design to test next is:

```text
planner expressions feed keyword search
original user question feeds vector search once
hybrid fuses keyword-expression results with one vector-question result
```

## Methodology Decisions

### Query Text Artifacts

For each case, prepare and freeze these inputs before running retrieval variants:

| Artifact | Source | Used by |
|---|---|---|
| `question_text` | Original Spider question | vector question-only policy, single keyword baseline |
| `planner_expressions` | LLM planner, 2-4 expressions | keyword multi policy, vector expression-each diagnostic |
| `planner_latency_ms` | LLM planner call | online e2e only for planner-based policies |

Planner output must be generated once per case and reused by all variants.

### Corpus Profiles

For each selected DB, prepare:

| Profile | Schema docs | AI metadata | Embeddings |
|---|---|---|---|
| `raw` | raw schema text | no | raw schema text |
| `enriched` | raw + AI fields | yes | raw + AI fields |

Hybrid variants may mix keyword and vector corpus profiles:

| Variant family | Keyword corpus | Vector corpus |
|---|---|---|
| raw | raw | raw |
| enriched | enriched | enriched |
| keyword-enriched-vector-raw | enriched | raw |
| keyword-raw-vector-enriched | raw | enriched |

### Query Policies

Introduce explicit query policy names. Do not overload `single` and `multi` alone.

| Policy | Planner | Keyword search input | Vector search input | Expected online embedding calls |
|---|---|---|---|---:|
| `single_question` | no | question | question | 1 for vector/hybrid, 0 for keyword |
| `multi_keyword_vector_question` | yes | each planner expression | original question only | 1 for vector/hybrid |
| `multi_keyword_vector_expression_each` | yes | each planner expression | each planner expression | N for vector/hybrid |

Interpretation:

- `single_question` is the simple baseline.
- `multi_keyword_vector_question` is the main realistic hybrid policy to evaluate.
- `multi_keyword_vector_expression_each` is a diagnostic/stress policy matching the current implementation.

### Retrieval Variants

Run these core variants first:

| Variant | Retriever | Keyword corpus | Vector corpus | Query policy |
|---|---|---|---|---|
| `keyword_raw_single` | keyword | raw | none | `single_question` |
| `keyword_enriched_single` | keyword | enriched | none | `single_question` |
| `keyword_raw_multi` | keyword | raw | none | `multi_keyword_vector_question` |
| `keyword_enriched_multi` | keyword | enriched | none | `multi_keyword_vector_question` |
| `vector_raw_question` | vector | none | raw | `single_question` |
| `vector_enriched_question` | vector | none | enriched | `single_question` |
| `hybrid_raw_vector_question` | hybrid | raw | raw | `multi_keyword_vector_question` |
| `hybrid_keyword_enriched_vector_raw_question` | hybrid | enriched | raw | `multi_keyword_vector_question` |
| `hybrid_keyword_raw_vector_enriched_question` | hybrid | raw | enriched | `multi_keyword_vector_question` |
| `hybrid_enriched_vector_question` | hybrid | enriched | enriched | `multi_keyword_vector_question` |

Run these diagnostic variants separately, not mixed into the main conclusion:

| Variant | Retriever | Keyword corpus | Vector corpus | Query policy |
|---|---|---|---|---|
| `vector_raw_expression_each` | vector | none | raw | `multi_keyword_vector_expression_each` |
| `vector_enriched_expression_each` | vector | none | enriched | `multi_keyword_vector_expression_each` |
| `hybrid_keyword_enriched_vector_raw_expression_each` | hybrid | enriched | raw | `multi_keyword_vector_expression_each` |
| `hybrid_enriched_expression_each` | hybrid | enriched | enriched | `multi_keyword_vector_expression_each` |

### Latency Accounting

Report online latency as staged timers:

| Field | Meaning |
|---|---|
| `planner_latency_ms` | LLM planner time, one call per case for planner policies |
| `question_embedding_ms` | embedding original user question |
| `expression_embedding_ms` | embedding planner expressions |
| `query_embedding_ms` | `question_embedding_ms + expression_embedding_ms` |
| `keyword_recall_ms` | keyword/FTS search time |
| `vector_recall_ms` | vector DB search time excluding query embedding |
| `hybrid_merge_ms` | within-search keyword/vector merge |
| `multi_fuse_ms` | fusing multiple query outputs |
| `retrieval_only_ms` | search work after planner, including embedding required by the selected query policy |
| `e2e_ms` | planner + retrieval-only for the selected online policy |

For quality comparison, retrieval should be evaluated with frozen planner outputs. For latency comparison, report both:

- `measured_provider_ms`: actual provider calls observed during the run.
- `modeled_online_ms`: the cost implied by the selected policy, counting only the calls an online agent would actually make once.

This avoids unfairly charging every variant for repeated identical embedding calls caused by benchmark matrix execution.

### Quality Metrics

For each variant and query policy:

- `table_recall_at_5`
- `column_recall_at_10`
- `mrr_table`
- `mrr_column`
- `failure_class_counts`
- `vector_available_rate`

For each run:

- selected DB counts
- case manifest path
- planner expression count distribution
- db search call count distribution
- embedding call count distribution

### Dataset Plan

Use staged dataset sizes:

| Stage | Cases | DBs | Purpose |
|---|---:|---:|---|
| smoke | 6 | 3 | wiring only |
| small | 24 | 3 | matrix sanity and obvious regressions |
| medium | 40 | 5 | first directional comparison |
| release | 100+ | 10+ | final decision support |

All stages must save a case manifest so follow-up runs use the exact same cases.

## Task 1: Mark Current Expression-Each Runs As Diagnostic

**Files:**
- Create: `reports/retrieval_ab_profile_matrix_mixed_spider40_rr5_real_provider/RUN_ABORTED_METHODOLOGY_REDESIGN.md`
- Modify: `reports/retrieval_ab_profile_matrix_mixed_spider24_rr3_real_provider/verification_report.md`

**Interfaces:**
- Produces: clear report labels so nobody reads current expression-each runs as final online evidence.

- [ ] **Step 1: Create the aborted-run note**

```markdown
# Run Aborted For Methodology Redesign

This run was stopped before completion after identifying a benchmark design issue:
current `multi` mode sends every planner expression through `db.search`.
For vector and hybrid, this means every expression is embedded separately.

Do not use this directory for final quality or latency conclusions.
Use it only as diagnostic evidence for the current `multi_keyword_vector_expression_each` policy.
```

- [ ] **Step 2: Update the 24-case verification report caveat**

Add:

```markdown
This 24-case run used `multi_keyword_vector_expression_each` for vector/hybrid multi-query rows.
It is valid as a diagnostic run, but it does not answer whether production hybrid should use
planner expressions for keyword only and the original question for vector.
```

- [ ] **Step 3: Verify**

Run:

```powershell
git diff -- reports/retrieval_ab_profile_matrix_mixed_spider24_rr3_real_provider/verification_report.md reports/retrieval_ab_profile_matrix_mixed_spider40_rr5_real_provider/RUN_ABORTED_METHODOLOGY_REDESIGN.md
```

Expected: only the explicit caveat/note is shown.

## Task 2: Add Explicit Query Policy Types

**Files:**
- Modify: `reports/retrieval_ab_ai_enrich_contrast/run_spider_ai_enrich_contrast.py`
- Test: `engine/tests/test_retrieval_ab_contrast.py`

**Interfaces:**
- Produces: `EvalVariant.query_policy: str`
- Produces: allowed values `single_question`, `multi_keyword_vector_question`, `multi_keyword_vector_expression_each`
- Produces: `_variant_dict()` includes `query_policy`

- [ ] **Step 1: Write failing tests**

Add tests asserting:

```python
variants = {variant.name: variant for variant in resolve_eval_variants(())}
assert variants["hybrid_keyword_enriched_vector_raw_question"].query_policy == "multi_keyword_vector_question"
assert variants["hybrid_keyword_enriched_vector_raw_expression_each"].query_policy == "multi_keyword_vector_expression_each"
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py::test_default_eval_variants_cover_query_policies -q
```

Expected: fail because `query_policy` does not exist.

- [ ] **Step 3: Implement minimal query policy field**

Add `query_policy` to `EvalVariant`, update defaults, and include it in `_variant_dict`.

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py -q
```

Expected: pass.

## Task 3: Split Keyword Expressions From Vector Expressions

**Files:**
- Modify: `engine/evaluation/retrieval_ab/cli.py`
- Test: `engine/tests/test_retrieval_ab_config_report_runner.py`

**Interfaces:**
- Modify `_run_ai_assisted_retrieval_case(...)` to accept:

```python
keyword_expressions: tuple[str, ...] | None = None
vector_expressions: tuple[str, ...] | None = None
```

- Produces event output:

```python
{
    "keyword_expressions": [...],
    "vector_expressions": [...],
    "query_policy": "multi_keyword_vector_question"
}
```

- [ ] **Step 1: Write failing test for vector question-only policy**

Use a monkeypatched `db_search` and assert the call sequence for hybrid:

```python
keyword_expressions = ("singer name", "concert stadium")
vector_expressions = ("How many singers performed in concerts?",)
```

Expected calls:

```python
[
    {"query": "singer name", "retrieval_leg": "keyword"},
    {"query": "concert stadium", "retrieval_leg": "keyword"},
    {"query": "How many singers performed in concerts?", "retrieval_leg": "vector"},
]
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_ai_assisted_retrieval_can_use_keyword_multi_and_vector_question_only -q
```

Expected: fail because the runner only accepts one expression list.

- [ ] **Step 3: Implement split expression execution**

Add a benchmark-only execution path that can call keyword and vector legs separately, then fuse outputs. Keep existing behavior available for `multi_keyword_vector_expression_each`.

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_ai_assisted_retrieval_can_use_keyword_multi_and_vector_question_only -q
```

Expected: pass.

## Task 4: Add Accurate Embedding Call Counts And Timers

**Files:**
- Modify: `engine/evaluation/retrieval_ab/cli.py`
- Modify: `reports/retrieval_ab_ai_enrich_contrast/run_spider_ai_enrich_contrast.py`
- Modify: `engine/evaluation/retrieval_ab/contrast.py`
- Test: `engine/tests/test_retrieval_ab_contrast.py`

**Interfaces:**
- Produces per-case fields:

```python
"planner_call_count": int
"question_embedding_call_count": int
"expression_embedding_call_count": int
"embedding_call_count": int
"db_search_call_count": int
"question_embedding_ms": float
"expression_embedding_ms": float
"query_embedding_ms": float
"multi_fuse_ms": float
```

- [ ] **Step 1: Write failing summary test**

Assert summary contains p95 for:

```python
p95_question_embedding_ms
p95_expression_embedding_ms
p95_multi_fuse_ms
avg_embedding_call_count
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py::test_summarize_contrast_rows_reports_query_policy_costs -q
```

Expected: fail because these fields are absent.

- [ ] **Step 3: Implement timers and call counts**

Populate fields from child search outputs and query policy metadata.

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py -q
```

Expected: pass.

## Task 5: Freeze Case Manifest, Planner Outputs, And Embedding Inputs

**Files:**
- Modify: `reports/retrieval_ab_ai_enrich_contrast/run_spider_ai_enrich_contrast.py`
- Test: `engine/tests/test_retrieval_ab_contrast.py`

**Interfaces:**
- Produces files in report dir:

```text
case_manifest.json
planner_outputs.json
embedding_inputs.json
```

- [ ] **Step 1: Write failing test**

Assert the runner writes:

```python
case_manifest.json
planner_outputs.json
embedding_inputs.json
```

and that every variant row references a `case_id` from `case_manifest.json`.

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py::test_runner_freezes_case_and_query_artifacts -q
```

Expected: fail because the artifacts are absent.

- [ ] **Step 3: Implement artifact writing**

Write selected cases, planner expressions, and policy-specific embedding inputs before matrix execution.

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py -q
```

Expected: pass.

## Task 6: Generate Methodology-Aware Reports

**Files:**
- Modify: `reports/retrieval_ab_ai_enrich_contrast/run_spider_ai_enrich_contrast.py`
- Test: `engine/tests/test_retrieval_ab_contrast.py`

**Interfaces:**
- Report sections:

```text
Prep
Query policy
Quality
Online latency
Provider/call counts
Caveats
Recommended production policy
```

- [ ] **Step 1: Write failing markdown test**

Assert markdown includes:

```text
query_policy
question_embedding_ms
expression_embedding_ms
embedding_call_count
modeled_online_ms
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py::test_markdown_report_includes_query_policy_latency_breakdown -q
```

Expected: fail because current markdown lacks the new policy/cost fields.

- [ ] **Step 3: Implement report update**

Add separate quality and latency tables. Do not mix diagnostic `expression_each` variants into the main recommendation table.

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_contrast.py -q
```

Expected: pass.

## Task 7: Run The Corrected Benchmark

**Files:**
- Create report directory under `reports/`

**Interfaces:**
- Produces final run directories:

```text
reports/retrieval_benchmark_policy_matrix_spider24_rr3_real_provider/
reports/retrieval_benchmark_policy_matrix_spider40_rr5_real_provider/
```

- [ ] **Step 1: Run 24/3 after methodology fixes**

Run with:

```powershell
DBFOX_EVAL_CASE_LIMIT=24
DBFOX_EVAL_DB_LIMIT=3
DBFOX_EVAL_SAMPLE_STRATEGY=round_robin_db
```

Expected:

```text
case_count=24
db_count=3
raw/enriched docs_equal_embeddings=true
query_policy present on every summary row
```

- [ ] **Step 2: Inspect 24/3**

Confirm:

```text
hybrid_keyword_enriched_vector_raw_question
  keyword datasource = enriched
  vector datasource = raw
  vector expression count = 1
  expression embedding call count = 0
```

- [ ] **Step 3: Run 40/5**

Run with:

```powershell
DBFOX_EVAL_CASE_LIMIT=40
DBFOX_EVAL_DB_LIMIT=5
DBFOX_EVAL_SAMPLE_STRATEGY=round_robin_db
```

Expected:

```text
case_count=40
db_count=5
all matrix cells complete
```

- [ ] **Step 4: Write final comparison**

Report:

```text
best keyword-only policy
best vector-only policy
best hybrid with vector question-only
diagnostic expression-each result
whether AI enrich should feed keyword, vector, both, or neither
```

## Self-Review

Spec coverage:
- Raw/enriched corpora and embeddings are covered.
- Keyword-only, vector-only, full hybrid, and mixed hybrid profiles are covered.
- Planner timing and query embedding timing are separated.
- The unfair multi-query vectorization issue is explicitly corrected with query policies.
- Current runs are labeled diagnostic, not final.

Placeholder scan:
- No task uses TBD/TODO/fill-in placeholders.

Type consistency:
- `query_policy`, `keyword_expressions`, `vector_expressions`, and latency field names are consistent across tasks.
