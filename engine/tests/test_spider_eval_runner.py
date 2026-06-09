from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from engine.evaluation.spider.spider_eval import (
    SpiderCaseResult,
    SpiderEvalRunner,
    SpiderEvalSummary,
    classify_failure,
    summarize_spider_results,
)
from engine.evaluation.spider.spider_loader import SpiderExample


# -- Fake runtime -----------------------------------------------------------


class _FakeResponse:
    def __init__(self, sql: str | None = None) -> None:
        self.sql = sql


def _fake_run_fn(sql: str, *, latency_ms: int = 100) -> Any:
    """Return a run_fn that produces a fixed predicted SQL."""
    def _run(example: SpiderExample) -> tuple[Any, list[dict], int]:
        response = _FakeResponse(sql=sql)
        events = [
            {"step": {"name": "generate_sql_candidate", "tool_name": "sql.generate", "sql": sql}},
            {"step": {"name": "validate_sql", "tool_name": "sql.validate", "safe_sql": sql}},
        ]
        return response, events, latency_ms
    return _run


# -- Tests ------------------------------------------------------------------


class TestSpiderEvalRunnerFake:
    def test_generates_result_with_predicted_sql(self) -> None:
        runner = SpiderEvalRunner(run_fn=_fake_run_fn("SELECT COUNT(*) FROM t"))
        example = SpiderExample(
            db_id="test", question="q", gold_sql="SELECT COUNT(*) FROM t", db_path=Path("/nonexistent"),
        )
        result = runner.run_example(example)
        assert result.generated_sql is True
        assert result.predicted_sql == "SELECT COUNT(*) FROM t"

    def test_no_predicted_sql_marks_failure(self) -> None:
        def _no_sql(_example: SpiderExample) -> tuple[Any, list[dict], int]:
            return _FakeResponse(), [], 50
        runner = SpiderEvalRunner(run_fn=_no_sql)
        example = SpiderExample(
            db_id="test", question="q", gold_sql="SELECT 1", db_path=Path("/nonexistent"),
        )
        result = runner.run_example(example)
        assert result.generated_sql is False
        assert result.error == "No predicted SQL."

    def test_exception_handled(self) -> None:
        def _blows_up(_example: SpiderExample) -> tuple[Any, list[dict], int]:
            raise RuntimeError("boom")
        runner = SpiderEvalRunner(run_fn=_blows_up)
        example = SpiderExample(
            db_id="test", question="q", gold_sql="SELECT 1", db_path=Path("/nonexistent"),
        )
        result = runner.run_example(example)
        assert result.generated_sql is False
        assert "boom" in (result.error or "")

    def test_execute_disabled_skips_comparison(self) -> None:
        runner = SpiderEvalRunner(run_fn=_fake_run_fn("SELECT 1"), execute=False)
        example = SpiderExample(
            db_id="test", question="q", gold_sql="SELECT 1", db_path=Path("/nonexistent"),
        )
        result = runner.run_example(example)
        assert result.generated_sql is True
        assert result.execution_success is False
        assert result.execution_match is False

    def test_tool_sequence_extracted(self) -> None:
        runner = SpiderEvalRunner(run_fn=_fake_run_fn("SELECT 1"))
        example = SpiderExample(
            db_id="test", question="q", gold_sql="SELECT 1", db_path=Path("/nonexistent"),
        )
        result = runner.run_example(example)
        assert result.tool_sequence is not None
        assert "sql.generate" in result.tool_sequence
        assert "sql.validate" in result.tool_sequence

    def test_empty_examples_produces_zero_summary(self) -> None:
        results: list[SpiderCaseResult] = []
        summary = summarize_spider_results(results)
        assert summary.total_cases == 0
        assert summary.generated_sql_rate == 0.0
        assert summary.execution_accuracy == 0.0

    def test_run_loads_tiny_fixture_and_produces_results(self) -> None:
        fixture_root = Path("engine/tests/fixtures/spider_tiny")
        if not fixture_root.exists():
            pytest.skip("Spider tiny fixture not found")
        runner = SpiderEvalRunner(run_fn=_fake_run_fn("SELECT 1"))
        results, summary = runner.run(fixture_root)
        assert len(results) == 5
        assert summary.total_cases == 5
        assert summary.generated_sql_cases == 5
        assert summary.generated_sql_rate == 1.0


class TestSpiderSummary:
    def test_all_match(self) -> None:
        results = [
            SpiderCaseResult(db_id="x", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=True, execution_match=True, latency_ms=100),
            SpiderCaseResult(db_id="y", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=True, execution_match=True, latency_ms=200),
        ]
        summary = summarize_spider_results(results)
        assert summary.execution_accuracy == 1.0
        assert summary.avg_latency_ms == 150.0

    def test_mixed(self) -> None:
        results = [
            SpiderCaseResult(db_id="x", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=True, execution_match=True, latency_ms=100),
            SpiderCaseResult(db_id="y", question="q", gold_sql="S", predicted_sql=None,
                             generated_sql=False, execution_success=False, execution_match=False, latency_ms=50),
            SpiderCaseResult(db_id="z", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=True, execution_match=False, latency_ms=150),
            SpiderCaseResult(db_id="w", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=False, execution_match=False, latency_ms=200),
        ]
        summary = summarize_spider_results(results)
        assert summary.total_cases == 4
        assert summary.generated_sql_rate == 0.75
        assert summary.execution_success_rate == 0.5
        assert summary.execution_accuracy == 0.25


class TestClassifyFailure:
    def test_no_predicted_sql(self) -> None:
        r = SpiderCaseResult(db_id="x", question="q", gold_sql="S", predicted_sql=None,
                             generated_sql=False, execution_success=False, execution_match=False, latency_ms=0)
        assert classify_failure(r) == "no_predicted_sql"

    def test_execution_error(self) -> None:
        r = SpiderCaseResult(db_id="x", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=False, execution_match=False, latency_ms=0)
        assert classify_failure(r) == "predicted_sql_execution_error"

    def test_result_mismatch(self) -> None:
        r = SpiderCaseResult(db_id="x", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=True, execution_match=False, latency_ms=0)
        assert classify_failure(r) == "execution_result_mismatch"

    def test_success_returns_none(self) -> None:
        r = SpiderCaseResult(db_id="x", question="q", gold_sql="S", predicted_sql="S",
                             generated_sql=True, execution_success=True, execution_match=True, latency_ms=0)
        assert classify_failure(r) is None


class TestSpiderE2E:
    @pytest.mark.e2e
    def test_spider_datasource_creation_and_sync(self, db_session) -> None:
        """Verify Spider SQLite datasource can be created and schema synced."""
        from engine.evaluation.spider.spider_eval import _ensure_spider_sqlite_datasource
        from engine.evaluation.spider.spider_loader import SpiderExample
        from engine.models import DataSource

        fixture_root = Path("engine/tests/fixtures/spider_tiny")
        if not fixture_root.exists():
            pytest.skip("Spider tiny fixture not found")

        db_path = fixture_root / "database" / "tiny_school" / "tiny_school.sqlite"
        example = SpiderExample(
            db_id="tiny_school", question="How many students?",
            gold_sql="SELECT COUNT(*) FROM students", db_path=db_path,
        )

        ds_id, tables = _ensure_spider_sqlite_datasource(db_session, example)
        assert ds_id.startswith("spider_tiny_school_")
        assert "students" in tables
        assert "courses" in tables

        ds = db_session.query(DataSource).filter(DataSource.id == ds_id).first()
        assert ds is not None
        assert ds.db_type == "sqlite"
        assert "tiny_school.sqlite" in ds.database_name

    @pytest.mark.e2e
    def test_spider_tiny_databox_schema_direct_counts_and_avg(self, db_session, monkeypatch) -> None:
        """DataBox mode should use schema_direct metadata and match tiny aggregate cases."""
        from engine.evaluation.spider.spider_eval import (
            SpiderEvalRunner,
            create_databox_sqlite_run_fn,
        )

        fixture_root = Path("engine/tests/fixtures/spider_tiny")
        if not fixture_root.exists():
            pytest.skip("Spider tiny fixture not found")

        def fake_schema_direct(*, question: str, schema_context: str, dialect: str, llm_config: dict):
            if "average score" in question.lower():
                sql = "SELECT AVG(score) FROM courses"
            else:
                sql = "SELECT COUNT(*) FROM students"
            return {
                "sql": sql,
                "model": "schema-direct-test",
                "mode": "schema_direct",
                "latencyMs": 1,
                "schemaValidationWarnings": [],
                "metadata": {
                    "generation_source": "schema_direct_llm",
                    "dialect": dialect,
                    "used_query_plan": False,
                    "used_renderer": False,
                    "used_demo_fallback": False,
                },
            }

        monkeypatch.setattr("engine.agent.tools.generate_sql_from_schema_context", fake_schema_direct)
        run_fn = create_databox_sqlite_run_fn(
            db_session=db_session,
            api_key="sk-test",
            api_base="https://test/v1",
            model_name="schema-direct-test",
            execute=True,
            max_steps=12,
        )
        runner = SpiderEvalRunner(run_fn=run_fn, execute=True, runner_mode="databox")
        results, summary = runner.run(fixture_root, limit=2)

        assert summary.runner_mode == "databox"
        assert summary.is_databox_score is True
        assert summary.execution_accuracy == 1.0
        assert all(r.generation_metadata is not None for r in results)
        for result in results:
            assert result.generation_metadata["generation_source"] == "schema_direct_llm"
            assert result.generation_metadata["used_renderer"] is False
            assert result.generation_metadata["used_demo_fallback"] is False

    @pytest.mark.e2e
    def test_spider_databox_run_with_api_key(self, db_session) -> None:
        """Full DataBox pipeline against Spider tiny fixture with real LLM."""
        import os
        api_key = os.environ.get("DATABOX_LLM_API_KEY")
        if not api_key:
            pytest.skip("DATABOX_LLM_API_KEY not set")

        from engine.evaluation.spider.spider_eval import (
            SpiderEvalRunner,
            create_databox_sqlite_run_fn,
        )

        fixture_root = Path("engine/tests/fixtures/spider_tiny")
        if not fixture_root.exists():
            pytest.skip("Spider tiny fixture not found")

        run_fn = create_databox_sqlite_run_fn(
            db_session=db_session,
            api_key=api_key,
            api_base=os.environ.get("DATABOX_LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            model_name=os.environ.get("DATABOX_LLM_MODEL", "qwen-plus"),
            execute=True,
            max_steps=20,
        )
        runner = SpiderEvalRunner(run_fn=run_fn, execute=True)
        results, summary = runner.run(fixture_root, limit=2)

        assert summary.total_cases == 2
        # With a real LLM, we expect at least some SQL generation
        generated = sum(1 for r in results if r.generated_sql)
        print(f"\nSpider DataBox: gen_sql={generated}/{summary.total_cases} "
              f"exec_acc={summary.execution_accuracy:.0%}")
        # Don't assert on accuracy — this is a real benchmark, not a unit test

    @pytest.mark.e2e
    def test_spider_cli_fake_mode_outputs_json(self) -> None:
        import subprocess
        import sys

        fixture_root = Path("engine/tests/fixtures/spider_tiny")
        if not fixture_root.exists():
            pytest.skip("Spider tiny fixture not found")

        result = subprocess.run(
            [sys.executable, "-m", "engine.evaluation.spider.spider_eval",
             "--spider-root", str(fixture_root), "--limit", "3", "--output", "-"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "total=3" in result.stdout
