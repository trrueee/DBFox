import pytest
from pathlib import Path
from engine.evaluation.spider.spider_eval import (
    SpiderEvalRunner,
    create_databox_sqlite_run_fn,
)

def test_debug_spider(db_session, monkeypatch):
    fixture_root = Path("engine/tests/fixtures/spider_tiny")

    def fake_schema_direct(*, question: str, schema_context: str, dialect: str, llm_config: dict):
        print(f"\n[fake_schema_direct] question: {repr(question)}")
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
            "metadata": {"generation_source": "schema_direct_llm"},
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
