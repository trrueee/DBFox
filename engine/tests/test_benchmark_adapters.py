"""Test benchmark adapters and importer."""
from __future__ import annotations

import json

from engine.evaluation.benchmarks.base import BenchmarkCase
from engine.evaluation.benchmarks.spider import SpiderAdapter
from engine.evaluation.benchmarks.bird import BIRDAdapter
from engine.evaluation.benchmarks.custom import CustomAdapter
from engine.evaluation.benchmarks.importer import import_benchmark_cases


def test_spider_adapter_payload():
    adapter = SpiderAdapter()
    payload = {
        "cases": [
            {
                "question": "What is the total number of users?",
                "query": "SELECT COUNT(*) FROM users",
                "db_id": "test_db",
                "difficulty": "easy",
            }
        ]
    }
    cases = adapter.load_cases(payload=payload, limit=5)
    assert len(cases) == 1
    case = cases[0]
    assert case.source == "spider"
    assert case.question == "What is the total number of users?"
    assert case.gold_sql == "SELECT COUNT(*) FROM users"
    assert case.db_id == "test_db"
    assert case.difficulty == "easy"


def test_bird_adapter_payload():
    adapter = BIRDAdapter()
    payload = {
        "cases": [
            {
                "question": "Find all orders in 2025",
                "SQL": "SELECT * FROM orders WHERE year = 2025",
                "db_id": "bird_db",
                "evidence": "orders table has year column",
                "difficulty": "moderate",
            }
        ]
    }
    cases = adapter.load_cases(payload=payload)
    assert len(cases) == 1
    case = cases[0]
    assert case.source == "bird"
    assert case.question == "Find all orders in 2025"
    assert case.gold_sql == "SELECT * FROM orders WHERE year = 2025"
    assert case.evidence == "orders table has year column"


def test_custom_adapter_payload():
    adapter = CustomAdapter()
    payload = {
        "cases": [
            {
                "id": "case-001",
                "question": "Custom benchmark question",
                "query": "SELECT 1",
                "tags": ["experimental"],
                "schema_payload": {"tables": ["t1", "t2"]},
            }
        ]
    }
    cases = adapter.load_cases(payload=payload)
    assert len(cases) == 1
    case = cases[0]
    assert case.source == "custom"
    assert case.source_case_id == "case-001"
    assert case.tags == ["custom", "experimental"]
    assert case.schema_payload == {"tables": ["t1", "t2"]}


def test_adapter_limit():
    adapter = SpiderAdapter()
    payload = {
        "cases": [
            {"question": f"q{i}"} for i in range(10)
        ]
    }
    cases = adapter.load_cases(payload=payload, limit=3)
    assert len(cases) == 3


def test_adapter_missing_path_returns_empty():
    adapter = SpiderAdapter()
    cases = adapter.load_cases(path="/nonexistent/path/spider.json")
    assert cases == []


def test_adapter_empty_payload():
    adapter = BIRDAdapter()
    cases = adapter.load_cases(payload={"cases": []})
    assert cases == []


def test_import_benchmark_cases_to_db(db_session, test_datasource):
    cases = [
        BenchmarkCase(
            source="spider",
            source_case_id="s1",
            db_id="test_db",
            question="How many users?",
            gold_sql="SELECT COUNT(*) FROM users",
            difficulty="easy",
        ),
        BenchmarkCase(
            source="spider",
            source_case_id="s2",
            db_id="test_db",
            question="List all orders",
            gold_sql="SELECT * FROM orders",
            difficulty="medium",
        ),
    ]
    tasks = import_benchmark_cases(
        db_session,
        datasource_id=test_datasource.id,
        project_id=None,
        source="spider",
        cases=cases,
    )
    assert len(tasks) == 2
    t1 = tasks[0]
    assert t1.source == "spider"
    assert t1.source_case_id == "s1"
    assert t1.datasource_id == test_datasource.id
    assert "spider" in json.loads(str(t1.tags_json))
    assert "easy" in json.loads(str(t1.tags_json))

    t2 = tasks[1]
    assert t2.source_case_id == "s2"
    assert "medium" in json.loads(str(t2.tags_json))

    # Verify defaults are set
    assert json.loads(str(t1.expected_tools_json)) == [
        "schema.build_context",
        "query_plan.build",
        "sql.generate_candidate",
        "sql.validate",
    ]
    assert json.loads(str(t1.forbidden_tools_json)) == [
        "@limit", "@chart", "@export", "backup.create", "backup.restore", "ddl.execute",
    ]


def test_imported_tasks_persist(db_session, test_datasource):
    cases = [BenchmarkCase(
        source="custom",
        source_case_id="c1",
        question="Test persist",
    )]
    tasks = import_benchmark_cases(db_session, test_datasource.id, None, "custom", cases)
    db_session.commit()

    from engine.models import AgentGoldenTask
    loaded = db_session.query(AgentGoldenTask).filter(AgentGoldenTask.id == tasks[0].id).first()
    assert loaded is not None
    assert loaded.name == "custom/c1"


def test_benchmark_case_defaults():
    case = BenchmarkCase(source="custom", source_case_id="test", question="q?")
    assert case.gold_sql is None
    assert case.evidence is None
    assert case.difficulty is None
    assert case.schema_payload == {}
    assert case.tags == []
