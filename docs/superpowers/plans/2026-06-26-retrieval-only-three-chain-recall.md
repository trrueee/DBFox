# Retrieval-Only Three-Chain Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a retrieval-only Spider A/B/n path that runs `keyword`, `vector`, and `hybrid` schema retrieval chains and writes reliable recall/failure reports without invoking the live Agent.

**Architecture:** Keep the first slice inside `engine.evaluation.retrieval_ab`. Extend metrics with explicit `mode`, `used_tables`, `used_columns`, and `failure_class`; extend reports with JSONL and failure breakdowns; add a direct `db_search` retrieval-only CLI branch that reuses Spider datasource registration and existing `RetrievalHit` event extraction.

**Tech Stack:** Python 3.12, pytest, SQLAlchemy session fixtures, existing DBFox `db_search`, existing Spider tiny fixtures, JSON/CSV markdown reports.

---

## Scope

This plan only implements the first stage requested by the user:

- Run three retrieval chains: `keyword`, `vector`, `hybrid`.
- Compare retrieved tables and columns against Spider gold SQL expected schema.
- Produce durable case-level reports and failure breakdowns.
- Avoid live Agent execution in retrieval-only mode.

This plan does not fix Agent/tool/database/environment issues. Those fixes start after the retrieval-only report shows which cases and failure classes matter most.

## File Structure

- Modify `engine/evaluation/retrieval_ab/metrics.py`: add `mode`, `used_tables`, `used_columns`, `failure_class`, failure counts, and retrieval-only classification.
- Modify `engine/evaluation/retrieval_ab/runner.py`: pass evaluation mode into `evaluate_case` and keep event extraction reusable for direct retrieval events.
- Modify `engine/evaluation/retrieval_ab/report.py`: add JSONL case output, CSV fields, and failure breakdown in summary JSON and markdown.
- Modify `engine/evaluation/retrieval_ab/config.py`: add explicit mode parsing.
- Modify `engine/evaluation/retrieval_ab/cli.py`: add `--mode retrieval-only|live` and implement direct `db_search` retrieval execution.
- Modify `engine/tests/test_retrieval_ab_metrics.py`: add classification tests.
- Modify `engine/tests/test_retrieval_ab_config_report_runner.py`: add config, report, JSONL, and CLI retrieval-only tests.

### Task 1: Metrics Fields And Retrieval-Only Classification

**Files:**
- Modify: `engine/evaluation/retrieval_ab/metrics.py`
- Test: `engine/tests/test_retrieval_ab_metrics.py`

- [ ] **Step 1: Write failing tests for retrieval-only success and miss classification**

Append these tests to `engine/tests/test_retrieval_ab_metrics.py`:

```python
def test_retrieval_only_case_marks_none_when_expected_schema_is_retrieved() -> None:
    result = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_tiny_school_001",
            db_id="tiny_school",
            variant="keyword",
            mode="retrieval-only",
            question="How many students are there?",
            expected_tables=("students",),
            expected_columns=("students.id",),
            retrieved_items=(
                RetrievalHit(type="table", table_name="students", score=10.0),
                RetrievalHit(type="column", table_name="students", column_name="id", score=9.0),
            ),
        )
    )

    assert result.failure_class == "none"
    assert result.failure_reason is None
    assert result.used_tables == ()
    assert result.used_columns == ()
    assert result.task_solved is False


def test_retrieval_only_case_marks_retrieval_miss_when_expected_table_is_absent() -> None:
    result = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_tiny_school_002",
            db_id="tiny_school",
            variant="vector",
            mode="retrieval-only",
            question="How many students are there?",
            expected_tables=("students",),
            expected_columns=("students.id",),
            retrieved_items=(RetrievalHit(type="table", table_name="teachers", score=10.0),),
        )
    )

    assert result.failure_class == "retrieval_miss"
    assert "missing expected tables in retrieval: students" in str(result.failure_reason)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_metrics.py::test_retrieval_only_case_marks_none_when_expected_schema_is_retrieved engine/tests/test_retrieval_ab_metrics.py::test_retrieval_only_case_marks_retrieval_miss_when_expected_table_is_absent -q
```

Expected: FAIL because `CaseEvaluationInput` does not accept `mode` and `CaseEvaluationResult` does not expose `failure_class`, `used_tables`, or `used_columns`.

- [ ] **Step 3: Add metrics fields and classifier**

In `engine/evaluation/retrieval_ab/metrics.py`, add these fields:

```python
@dataclass(frozen=True)
class CaseEvaluationInput:
    case_id: str
    db_id: str
    variant: str
    question: str
    expected_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    retrieved_items: tuple[RetrievalHit, ...]
    mode: str = "live"
    actual_sql: str | None = None
    query_execution_success: bool = False
    latency_ms: int = 0
    retrieval_latency_ms: float = 0.0
    embedding_build_time_ms: float = 0.0
    vector_available: bool | None = None
    step_count: int = 0
    tool_call_count: int = 0
    db_search_call_count: int = 0
    schema_observe_count: int = 0
    replan_count: int = 0
    clarification_count: int = 0
    safety_violation_count: int = 0
    answer_grounded: bool | None = None
    failure_reason: str | None = None
```

Add these fields to `CaseEvaluationResult`:

```python
    mode: str
    used_tables: tuple[str, ...]
    used_columns: tuple[str, ...]
    failure_class: str
```

In `evaluate_case`, normalize mode and compute used schema:

```python
    mode = str(payload.mode or "live").strip().lower()
    actual_schema = extract_expected_schema_from_sql(payload.actual_sql or "")
    actual_tables = set(actual_schema.tables)
    actual_columns = set(actual_schema.columns)
    used_tables = tuple(sorted(actual_tables))
    used_columns = tuple(sorted(actual_columns))
```

Replace the current failure assignment with:

```python
    failure_reason = payload.failure_reason or _failure_reason(
        task_solved=task_solved,
        missing_key_table=missing_key_table,
        wrong_table=wrong_table,
        query_generated=query_generated,
        query_execution_success=payload.query_execution_success,
        safety_violation_count=payload.safety_violation_count,
        expected_tables=expected_table_set,
        retrieved_tables=table_top5,
        actual_tables=actual_tables,
        mode=mode,
    )
    failure_class = _failure_class(
        mode=mode,
        task_solved=task_solved,
        table_recall_at_5=table_recall_at_5,
        column_recall_at_10=column_recall_at_10,
        query_generated=query_generated,
        query_execution_success=payload.query_execution_success,
        safety_violation_count=payload.safety_violation_count,
        failure_reason=failure_reason,
    )
```

Return the new fields:

```python
        mode=mode,
        used_tables=used_tables,
        used_columns=used_columns,
        failure_class=failure_class,
```

Update `_failure_reason` signature with `mode: str`, and make no-SQL irrelevant in retrieval-only mode:

```python
    if not query_generated and mode != "retrieval-only":
        reasons.append("no query generated")
    if query_generated and not query_execution_success:
        reasons.append("query execution failed")
```

Add this helper:

```python
def _failure_class(
    *,
    mode: str,
    task_solved: bool,
    table_recall_at_5: bool,
    column_recall_at_10: bool,
    query_generated: bool,
    query_execution_success: bool,
    safety_violation_count: int,
    failure_reason: str | None,
) -> str:
    if mode == "retrieval-only":
        if table_recall_at_5 and column_recall_at_10 and not failure_reason:
            return "none"
        if not table_recall_at_5 or not column_recall_at_10:
            return "retrieval_miss"
    if task_solved:
        return "none"
    text = (failure_reason or "").lower()
    if "unknown tool" in text:
        return "unknown_tool"
    if "policygate" in text or "policy gate" in text or "blocked" in text:
        return "policy_gate_block"
    if "recursion limit" in text or "loop prevention" in text or "repeated with same args" in text:
        return "agent_loop_or_recursion"
    if "ilike" in text or "invalid sql identifier" in text or "ambiguous column" in text or "schema validation parse error" in text:
        return "sql_compatibility"
    if "timeout" in text or "upstream" in text or "connection" in text or "internalservererror" in text:
        return "model_or_infra_error"
    if safety_violation_count:
        return "policy_gate_block"
    if not table_recall_at_5 or not column_recall_at_10:
        return "retrieval_miss"
    if not query_generated:
        return "agent_no_sql"
    if query_generated and not query_execution_success:
        return "query_execution_failed"
    return "unknown"
```

- [ ] **Step 4: Run metrics tests**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_metrics.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit metrics changes**

Run:

```powershell
git add engine/evaluation/retrieval_ab/metrics.py engine/tests/test_retrieval_ab_metrics.py
git commit -m "feat: classify retrieval ab case failures"
```

### Task 2: Failure Breakdown And JSONL Reports

**Files:**
- Modify: `engine/evaluation/retrieval_ab/metrics.py`
- Modify: `engine/evaluation/retrieval_ab/report.py`
- Test: `engine/tests/test_retrieval_ab_config_report_runner.py`

- [ ] **Step 1: Write failing report tests**

Update `test_write_reports_outputs_summary_json_cases_csv_and_markdown` in `engine/tests/test_retrieval_ab_config_report_runner.py` so it asserts JSONL and failure fields:

```python
    assert paths.cases_jsonl.name == "spider_keyword_cases.jsonl"
    jsonl_rows = [
        json.loads(line)
        for line in paths.cases_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert jsonl_rows[0]["failure_class"] == "none"
    assert json.loads(paths.summary_json.read_text(encoding="utf-8"))["summaries"][0]["failure_class_counts"] == {"none": 1}
    assert "failure_class" in csv_text
    assert "used_tables" in csv_text
    assert "Failure breakdown" in md_text
```

- [ ] **Step 2: Run the report test and verify it fails**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_write_reports_outputs_summary_json_cases_csv_and_markdown -q
```

Expected: FAIL because `ReportPaths.cases_jsonl` and failure summary fields do not exist.

- [ ] **Step 3: Add failure counts to summaries**

In `engine/evaluation/retrieval_ab/metrics.py`, add these fields to `VariantSummary`:

```python
    failure_class_counts: dict[str, int]
    failure_class_rates: dict[str, float]
```

In `summarize_variant`, compute counts and rates:

```python
    failure_counts: dict[str, int] = {}
    for row in rows:
        failure_counts[row.failure_class] = failure_counts.get(row.failure_class, 0) + 1
    failure_rates = {
        key: round(value / total, 4) if total else 0.0
        for key, value in sorted(failure_counts.items())
    }
```

Return:

```python
        failure_class_counts=dict(sorted(failure_counts.items())),
        failure_class_rates=failure_rates,
```

- [ ] **Step 4: Add JSONL report output**

In `engine/evaluation/retrieval_ab/report.py`, extend `ReportPaths`:

```python
@dataclass(frozen=True)
class ReportPaths:
    summary_json: Path
    cases_csv: Path
    cases_jsonl: Path
    markdown_report: Path
```

In `write_reports`, add:

```python
    cases_jsonl_path = out / f"{prefix}_cases.jsonl"
```

Call a new writer:

```python
    _write_cases_jsonl(cases_jsonl_path, case_rows)
```

Return:

```python
    return ReportPaths(
        summary_json=summary_path,
        cases_csv=cases_path,
        cases_jsonl=cases_jsonl_path,
        markdown_report=markdown_path,
    )
```

Add:

```python
def _write_cases_jsonl(path: Path, cases: tuple[CaseEvaluationResult, ...]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(asdict(case), ensure_ascii=False) + "\n")
```

- [ ] **Step 5: Add CSV fields and markdown breakdown**

In `_write_cases_csv`, include:

```python
        "mode",
        "used_tables",
        "used_columns",
        "failure_class",
```

Add this section to `_render_markdown` after the main table:

```python
    lines.extend(["", "## Failure breakdown", ""])
    lines.append("| variant | failure_class | count | rate |")
    lines.append("| --- | --- | ---: | ---: |")
    for row in summaries:
        for failure_class, count in row.failure_class_counts.items():
            rate = row.failure_class_rates.get(failure_class, 0.0)
            lines.append(f"| {row.variant} | {failure_class} | {count} | {_pct(rate)} |")
```

- [ ] **Step 6: Run report tests**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_write_reports_outputs_summary_json_cases_csv_and_markdown -q
```

Expected: PASS.

- [ ] **Step 7: Commit report changes**

Run:

```powershell
git add engine/evaluation/retrieval_ab/metrics.py engine/evaluation/retrieval_ab/report.py engine/tests/test_retrieval_ab_config_report_runner.py
git commit -m "feat: write retrieval ab failure reports"
```

### Task 3: Explicit Evaluation Mode Configuration

**Files:**
- Modify: `engine/evaluation/retrieval_ab/config.py`
- Modify: `engine/evaluation/retrieval_ab/cli.py`
- Test: `engine/tests/test_retrieval_ab_config_report_runner.py`

- [ ] **Step 1: Write failing config test**

Append this test to `engine/tests/test_retrieval_ab_config_report_runner.py`:

```python
def test_config_reads_explicit_retrieval_only_mode() -> None:
    cfg = RetrievalAbConfig.from_mapping(
        {"benchmark": "spider", "variants": "keyword,vector,hybrid", "mode": "retrieval-only"},
        env={},
    )

    assert cfg.mode == "retrieval-only"
    assert cfg.variants == ("keyword", "vector", "hybrid")
```

- [ ] **Step 2: Run the config test and verify it fails**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_config_reads_explicit_retrieval_only_mode -q
```

Expected: FAIL because `RetrievalAbConfig.mode` does not exist.

- [ ] **Step 3: Add config mode parsing**

In `engine/evaluation/retrieval_ab/config.py`, add `mode` to `RetrievalAbConfig`:

```python
    mode: str
```

In `from_mapping`, set:

```python
            mode=_normalize_mode(values.get("mode") or source_env.get("DBFOX_RETRIEVAL_AB_MODE") or "live"),
```

Add:

```python
def _normalize_mode(value: Any) -> str:
    mode = str(value or "live").strip().lower().replace("_", "-")
    if mode not in {"live", "retrieval-only"}:
        raise ValueError("Retrieval A/B mode must be 'live' or 'retrieval-only'.")
    return mode
```

- [ ] **Step 4: Add CLI argument**

In `engine/evaluation/retrieval_ab/cli.py`, add:

```python
    parser.add_argument("--mode", choices=("live", "retrieval-only"), default=None)
```

- [ ] **Step 5: Run config test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_config_reads_explicit_retrieval_only_mode -q
```

Expected: PASS.

- [ ] **Step 6: Commit config changes**

Run:

```powershell
git add engine/evaluation/retrieval_ab/config.py engine/evaluation/retrieval_ab/cli.py engine/tests/test_retrieval_ab_config_report_runner.py
git commit -m "feat: configure retrieval ab mode"
```

### Task 4: Direct Retrieval-Only Runner

**Files:**
- Modify: `engine/evaluation/retrieval_ab/runner.py`
- Modify: `engine/evaluation/retrieval_ab/cli.py`
- Test: `engine/tests/test_retrieval_ab_config_report_runner.py`

- [ ] **Step 1: Write failing unit test for direct retrieval events**

Append this test to `engine/tests/test_retrieval_ab_config_report_runner.py`:

```python
def test_run_retrieval_only_case_returns_db_search_artifacts(monkeypatch) -> None:
    case = EvaluationCase(
        case_id="spider_tiny_school_001",
        db_id="tiny_school",
        question="How many students?",
        gold_sql="SELECT COUNT(*) FROM students",
        expected_tables=("students",),
        expected_columns=(),
    )

    def fake_db_search(_session, datasource_id: str, query: str, limit: int):
        return {
            "engine": "keyword",
            "original_query": query,
            "limit": limit,
            "retrieval_latency_ms": 12.0,
            "embedding_build_time_ms": 0.0,
            "vector_available": None,
            "results": [{"type": "table", "table_name": "students", "score": 10.0}],
        }

    monkeypatch.setattr(retrieval_cli, "db_search", fake_db_search)

    artifacts = retrieval_cli._run_retrieval_only_case(
        db_session=object(),
        datasource_id="ds-tiny",
        case=case,
        limit=5,
    )

    assert artifacts.actual_sql is None
    assert artifacts.query_execution_success is False
    assert artifacts.latency_ms == 12
    assert artifacts.events[0]["step"]["tool_name"] == "db.search"
    assert artifacts.events[0]["step"]["output"]["results"][0]["table_name"] == "students"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_run_retrieval_only_case_returns_db_search_artifacts -q
```

Expected: FAIL because `_run_retrieval_only_case` does not exist.

- [ ] **Step 3: Pass mode through `evaluate_artifacts`**

In `engine/evaluation/retrieval_ab/runner.py`, update `evaluate_artifacts` signature:

```python
def evaluate_artifacts(
    case: EvaluationCase,
    variant: str,
    artifacts: AgentRunArtifacts,
    *,
    mode: str = "live",
) -> CaseEvaluationResult:
```

Pass mode into `CaseEvaluationInput`:

```python
            mode=mode,
```

In `RetrievalAbRunner.run`, keep existing behavior by calling:

```python
                results.append(evaluate_artifacts(case, variant, artifacts, mode="live"))
```

- [ ] **Step 4: Implement direct retrieval artifacts**

In `engine/evaluation/retrieval_ab/cli.py`, import `db_search`:

```python
from engine.tools.db.search import db_search
```

Add:

```python
def _run_retrieval_only_case(
    *,
    db_session: Session,
    datasource_id: str,
    case: Any,
    limit: int,
) -> AgentRunArtifacts:
    started = time.perf_counter()
    output = db_search(db_session, datasource_id, case.question, limit)
    latency_ms = int(round(float(output.get("retrieval_latency_ms") or ((time.perf_counter() - started) * 1000))))
    error = str(output.get("error")) if output.get("error") else None
    return AgentRunArtifacts(
        actual_sql=None,
        query_execution_success=False,
        events=({"step": {"tool_name": "db.search", "output": output}},),
        latency_ms=latency_ms,
        error=error,
    )
```

- [ ] **Step 5: Run direct retrieval test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_run_retrieval_only_case_returns_db_search_artifacts -q
```

Expected: PASS.

- [ ] **Step 6: Commit runner changes**

Run:

```powershell
git add engine/evaluation/retrieval_ab/runner.py engine/evaluation/retrieval_ab/cli.py engine/tests/test_retrieval_ab_config_report_runner.py
git commit -m "feat: add retrieval only case runner"
```

### Task 5: CLI Retrieval-Only Flow For Three Variants

**Files:**
- Modify: `engine/evaluation/retrieval_ab/cli.py`
- Test: `engine/tests/test_retrieval_ab_config_report_runner.py`

- [ ] **Step 1: Write failing CLI test that avoids live Agent**

Append this test to `engine/tests/test_retrieval_ab_config_report_runner.py`:

```python
def test_cli_retrieval_only_runs_three_variants_without_live_agent(tmp_path: Path, monkeypatch) -> None:
    cases_path = tmp_path / "dev.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "db_id": "tiny_school",
                    "question": "How many students are there?",
                    "query": "SELECT COUNT(*) FROM students",
                }
            ]
        ),
        encoding="utf-8",
    )

    class FakeSession:
        def close(self) -> None:
            pass

        def get_bind(self):
            return None

    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(retrieval_cli, "_create_temp_metadata_session", lambda _path: FakeSession())
    monkeypatch.setattr(
        retrieval_cli,
        "_load_examples_for_cases",
        lambda *_args, **_kwargs: (object(),),
    )
    monkeypatch.setattr(
        retrieval_cli,
        "_ensure_spider_sqlite_datasource",
        lambda _session, _example: ("ds-tiny", ["students"]),
    )

    def fake_run_retrieval_only_case(*, db_session, datasource_id: str, case: EvaluationCase, limit: int):
        calls.append((os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"], case.case_id))
        return AgentRunArtifacts(
            actual_sql=None,
            query_execution_success=False,
            events=(
                {
                    "step": {
                        "tool_name": "db.search",
                        "output": {
                            "retrieval_latency_ms": 1.0,
                            "embedding_build_time_ms": 0.0,
                            "results": [{"type": "table", "table_name": "students"}],
                        },
                    }
                },
            ),
        )

    monkeypatch.setattr(retrieval_cli, "_run_retrieval_only_case", fake_run_retrieval_only_case)

    def fail_live_call(*_args, **_kwargs):
        raise AssertionError("retrieval-only mode should not create or call live Agent")

    monkeypatch.setattr(retrieval_cli, "create_dbfox_sqlite_run_fn", fail_live_call)

    assert retrieval_cli.main(
        [
            "--benchmark",
            "spider",
            "--cases",
            str(cases_path),
            "--variants",
            "keyword,vector,hybrid",
            "--mode",
            "retrieval-only",
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    ) == 0

    assert calls == [
        ("keyword", "spider_tiny_school_001"),
        ("vector", "spider_tiny_school_001"),
        ("hybrid", "spider_tiny_school_001"),
    ]
    csv_text = (tmp_path / "reports" / "spider_keyword_vector_hybrid_cases.csv").read_text(encoding="utf-8")
    assert "keyword" in csv_text
    assert "vector" in csv_text
    assert "hybrid" in csv_text
```

- [ ] **Step 2: Run the CLI test and verify it fails**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_cli_retrieval_only_runs_three_variants_without_live_agent -q
```

Expected: FAIL because the CLI always prepares the live Agent run function.

- [ ] **Step 3: Branch CLI by mode**

In `engine/evaluation/retrieval_ab/cli.py`, change the main loop so live Agent setup only happens in live mode:

```python
            run_fn = None
            if cfg.mode == "live":
                run_fn = create_dbfox_sqlite_run_fn(
                    db_session=db_session,
                    api_key=os.getenv("OPENAI_API_KEY"),
                    api_base=os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE"),
                    model_name=cfg.model,
                    execute=cfg.execute,
                    pre_run=_prewarm_schema_embeddings_if_needed,
                )
            for variant in cfg.variants:
                os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = variant
                for case, example in zip(cases, examples, strict=True):
                    if cfg.mode == "retrieval-only":
                        datasource_id, _synced_tables = _ensure_spider_sqlite_datasource(db_session, example)
                        artifacts = _run_retrieval_only_case(
                            db_session=db_session,
                            datasource_id=datasource_id,
                            case=case,
                            limit=cfg.retrieval_top_k,
                        )
                    else:
                        artifacts = (
                            _run_live_case(run_fn, example, execute=cfg.execute)
                            if cfg.execute
                            else AgentRunArtifacts(
                                actual_sql=None,
                                query_execution_success=False,
                                error="Execution disabled. Re-run with --execute for live Agent evaluation.",
                            )
                        )
                    results.append(evaluate_artifacts(case, variant, artifacts, mode=cfg.mode))
```

Keep `_ensure_spider_sqlite_datasource` imported through the existing `create_dbfox_sqlite_run_fn` module import context:

```python
from engine.evaluation.spider.spider_eval import create_dbfox_sqlite_run_fn, _ensure_spider_sqlite_datasource
```

- [ ] **Step 4: Run CLI retrieval-only test**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py::test_cli_retrieval_only_runs_three_variants_without_live_agent -q
```

Expected: PASS.

- [ ] **Step 5: Commit CLI retrieval-only flow**

Run:

```powershell
git add engine/evaluation/retrieval_ab/cli.py engine/tests/test_retrieval_ab_config_report_runner.py
git commit -m "feat: run retrieval only ab variants"
```

### Task 6: Verification And First Retrieval-Only Smoke Run

**Files:**
- Test: `engine/tests/test_retrieval_ab_config_report_runner.py`
- Test: `engine/tests/test_retrieval_ab_metrics.py`
- Test: `engine/tests/test_retrieval_ab_variants.py`
- Test: `engine/tests/test_schema_vector_search.py`

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
python -m pytest engine/tests/test_retrieval_ab_config_report_runner.py engine/tests/test_retrieval_ab_metrics.py engine/tests/test_retrieval_ab_variants.py engine/tests/test_schema_vector_search.py -q
```

Expected: PASS.

- [ ] **Step 2: Run retrieval-only keyword smoke without model calls**

Run:

```powershell
python -m engine.evaluation.retrieval_ab.cli --benchmark spider --cases engine/tests/fixtures/spider_tiny/dev.json --variants keyword --mode retrieval-only --limit 2 --report-dir reports/retrieval_ab_smoke_keyword
```

Expected: command exits 0 and prints paths for summary, cases, and report.

- [ ] **Step 3: Run retrieval-only three-chain smoke when embedding credentials are configured**

Run:

```powershell
python -m engine.evaluation.retrieval_ab.cli --benchmark spider --cases engine/tests/fixtures/spider_tiny/dev.json --variants keyword,vector,hybrid --mode retrieval-only --limit 2 --report-dir reports/retrieval_ab_smoke_three_chain
```

Expected with embedding credentials: command exits 0 and the CSV contains `keyword`, `vector`, and `hybrid` rows.

Expected without embedding credentials: command exits 0; `vector` and `hybrid` rows may classify vector unavailability through `failure_reason` while still writing CSV, JSONL, summary JSON, and markdown.

- [ ] **Step 4: Inspect generated report artifacts**

Run:

```powershell
Get-ChildItem -LiteralPath reports/retrieval_ab_smoke_three_chain
Get-Content -LiteralPath reports/retrieval_ab_smoke_three_chain/spider_keyword_vector_hybrid_report.md -TotalCount 80
```

Expected: report includes variant recall metrics and a failure breakdown table.

- [ ] **Step 5: Commit verification adjustments if the smoke run required test-only fixes**

If no files changed during verification, skip this commit. If small fixes were required, run:

```powershell
git status --short
git add engine/evaluation/retrieval_ab engine/tests/test_retrieval_ab_config_report_runner.py engine/tests/test_retrieval_ab_metrics.py
git commit -m "test: verify retrieval only ab smoke"
```

## Follow-Up Phase

After this plan is complete, use the generated retrieval-only reports to choose the next repair target:

- Tool design and PolicyGate/tool contract issues.
- SQLite/Spider SQL compatibility, including identifiers and dialect operators.
- Environment context injection and `environment.get_profile` visibility.
- Agent loop convergence and fail-fast behavior.

Those repairs should each get a focused debugging pass and tests based on the dominant failure class from the retrieval-only and live reports.
