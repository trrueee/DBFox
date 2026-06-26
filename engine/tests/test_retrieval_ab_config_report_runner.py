from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import text as sa_text

from engine.evaluation.retrieval_ab.config import RetrievalAbConfig, load_env_file
from engine.evaluation.retrieval_ab import cli as retrieval_cli
from engine.evaluation.retrieval_ab.metrics import (
    CaseEvaluationInput,
    RetrievalHit,
    evaluate_case,
    summarize_variant,
)
from engine.evaluation.retrieval_ab.report import write_reports
from engine.evaluation.retrieval_ab.runner import (
    AgentRunArtifacts,
    RetrievalAbRunner,
    collect_db_search_metrics,
    collect_db_search_results,
    count_tool_calls,
)
from engine.evaluation.retrieval_ab.spider_fixture import EvaluationCase, make_spider_case


def test_config_reads_variants_and_top_k_from_args_with_env_defaults(tmp_path: Path) -> None:
    cfg = RetrievalAbConfig.from_mapping(
        {
            "benchmark": "spider",
            "cases": str(tmp_path / "dev.json"),
            "dbs": "concert_singer,pets_1",
            "variants": "keyword,hybrid",
            "model": "qwen-plus",
            "execute": True,
        },
        env={
            "DBFOX_RETRIEVAL_TOP_K": "20",
            "DBFOX_RETRIEVAL_VECTOR_TOP_K": "30",
            "DBFOX_RETRIEVAL_KEYWORD_TOP_K": "25",
            "DBFOX_EVAL_TEMPERATURE": "0",
        },
    )

    assert cfg.benchmark == "spider"
    assert cfg.cases_path == tmp_path / "dev.json"
    assert cfg.db_ids == ("concert_singer", "pets_1")
    assert cfg.variants == ("keyword", "hybrid")
    assert cfg.model == "qwen-plus"
    assert cfg.execute is True
    assert cfg.retrieval_top_k == 20
    assert cfg.vector_top_k == 30
    assert cfg.keyword_top_k == 25
    assert cfg.temperature == 0


def test_config_defaults_cases_to_spider_root_env() -> None:
    cfg = RetrievalAbConfig.from_mapping(
        {"benchmark": "spider", "variants": "keyword"},
        env={"DBFOX_SPIDER_ROOT": r"C:\Spider"},
    )

    assert cfg.cases_path == Path(r"C:\Spider") / "dev.json"


def test_config_default_cases_no_longer_uses_agent_eval_spider() -> None:
    cfg = RetrievalAbConfig.from_mapping({"benchmark": "spider", "variants": "keyword"}, env={})

    assert ".agent_eval" not in str(cfg.cases_path)
    assert cfg.cases_path.as_posix().endswith("engine/tests/fixtures/spider_tiny/dev.json")


def test_config_reads_explicit_retrieval_only_mode() -> None:
    cfg = RetrievalAbConfig.from_mapping(
        {"benchmark": "spider", "variants": "keyword,vector,hybrid", "mode": "retrieval-only"},
        env={},
    )

    assert cfg.mode == "retrieval-only"
    assert cfg.variants == ("keyword", "vector", "hybrid")


def test_config_reads_explicit_ai_assisted_retrieval_mode() -> None:
    cfg = RetrievalAbConfig.from_mapping(
        {"benchmark": "spider", "variants": "keyword,vector,hybrid", "mode": "ai-assisted-retrieval"},
        env={},
    )

    assert cfg.mode == "ai-assisted-retrieval"
    assert cfg.variants == ("keyword", "vector", "hybrid")


def test_load_env_file_sets_missing_values_without_overriding(tmp_path: Path) -> None:
    env_file = tmp_path / "dbfox-eval.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=fake-key",
                "OPENAI_BASE_URL=https://example.test/v1",
                "OPENAI_MODEL_NAME=qwen-plus",
                "IGNORED_LINE",
                "# comment",
            ]
        ),
        encoding="utf-8",
    )
    env = {"OPENAI_API_KEY": "already-set"}

    loaded = load_env_file(env_file, env=env)

    assert loaded is True
    assert env["OPENAI_API_KEY"] == "already-set"
    assert env["OPENAI_BASE_URL"] == "https://example.test/v1"
    assert env["OPENAI_MODEL_NAME"] == "qwen-plus"
    assert "IGNORED_LINE" not in env


def test_make_spider_case_uses_gold_sql_when_expected_fields_are_missing() -> None:
    raw = {
        "db_id": "concert_singer",
        "question": "Which singers performed in 2014?",
        "query": (
            "SELECT singer.name FROM singer "
            "JOIN singer_in_concert ON singer.singer_id = singer_in_concert.singer_id "
            "JOIN concert ON singer_in_concert.concert_id = concert.concert_id "
            "WHERE concert.year = 2014"
        ),
        "difficulty": "medium",
        "tags": ["join"],
    }

    case = make_spider_case(raw, index=1)

    assert case.case_id == "spider_concert_singer_001"
    assert case.db_id == "concert_singer"
    assert case.expected_tables == ("concert", "singer", "singer_in_concert")
    assert "concert.year" in case.expected_columns
    assert case.tags == ("join",)


def test_collect_db_search_results_reads_agent_events_in_rank_order() -> None:
    events = [
        {"step": {"tool_name": "model.sql_draft", "output": {"sql": "SELECT 1"}}},
        {
            "step": {
                "tool_name": "db.search",
                "output": {
                    "results": [
                        {"type": "table", "table_name": "singer", "score": 9.0},
                        {
                            "type": "column",
                            "table_name": "concert",
                            "column_name": "year",
                            "score": 8.0,
                            "matched_fields": ["column_name"],
                        },
                    ]
                },
            }
        },
    ]

    hits = collect_db_search_results(events)

    assert tuple(hit.ref for hit in hits) == ("singer", "concert.year")
    assert tuple(hit.rank for hit in hits) == (1, 2)
    assert count_tool_calls(events) == 2
    assert count_tool_calls(events, "db.search") == 1


def test_collect_db_search_results_prefers_fused_multi_query_event() -> None:
    events = [
        {
            "step": {
                "tool_name": "db.search",
                "input": {"query": "student entity"},
                "output": {
                    "results": [
                        {"type": "table", "table_name": "teachers", "score": 10.0},
                    ]
                },
            }
        },
        {
            "step": {
                "tool_name": "db.search.fused",
                "output": {
                    "search_expressions": ["student entity", "student names"],
                    "results": [
                        {"type": "table", "table_name": "students", "score": 0.05},
                        {"type": "column", "table_name": "students", "column_name": "name", "score": 0.04},
                    ],
                },
            }
        },
    ]

    hits = collect_db_search_results(events)

    assert tuple(hit.ref for hit in hits) == ("students", "students.name")
    assert tuple(hit.rank for hit in hits) == (1, 2)


def test_collect_db_search_metrics_sums_trace_fields_without_secret_leaks() -> None:
    events = [
        {
            "step": {
                "tool_name": "schema.embedding.prewarm",
                "output": {
                    "retrieval_latency_ms": 5.0,
                    "embedding_build_time_ms": 2.0,
                    "vector_available": True,
                },
            }
        },
        {
            "step": {
                "tool_name": "db.search",
                "output": {
                    "retrieval_latency_ms": 12.5,
                    "embedding_build_time_ms": 3.0,
                    "vector_available": True,
                    "error": "Vector retrieval unavailable. Check embedding configuration and provider connectivity.",
                },
            }
        },
        {
            "step": {
                "tool_name": "db.search",
                "output": {
                    "retrieval_latency_ms": 7.5,
                    "embedding_build_time_ms": 0.0,
                    "vector_available": True,
                },
            }
        },
    ]

    metrics = collect_db_search_metrics(events)

    assert metrics.retrieval_latency_ms == 25.0
    assert metrics.embedding_build_time_ms == 5.0
    assert metrics.vector_available is True


def test_runner_reuses_same_case_iterable_for_every_variant() -> None:
    case = EvaluationCase(
        case_id="spider_tiny_school_001",
        db_id="tiny_school",
        question="How many students?",
        gold_sql="SELECT COUNT(*) FROM students",
        expected_tables=("students",),
        expected_columns=(),
    )

    def run_case(_case: EvaluationCase, _variant: str) -> AgentRunArtifacts:
        return AgentRunArtifacts(
            actual_sql="SELECT COUNT(*) FROM students",
            query_execution_success=True,
            events=({"step": {"tool_name": "db.search", "output": {"results": [{"type": "table", "table_name": "students"}]}}},),
        )

    runner = RetrievalAbRunner(run_case)
    results, summaries = runner.run((item for item in (case,)), variants=("keyword", "vector"))

    assert tuple(result.variant for result in results) == ("keyword", "vector")
    assert tuple(summary.variant for summary in summaries) == ("keyword", "vector")


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
            "datasource_id": datasource_id,
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


def test_run_ai_assisted_retrieval_case_uses_planned_expressions_and_fused_results(monkeypatch) -> None:
    case = EvaluationCase(
        case_id="spider_tiny_school_003",
        db_id="tiny_school",
        question="List all student names.",
        gold_sql="SELECT name FROM students",
        expected_tables=("students",),
        expected_columns=("students.name",),
    )
    calls: list[str] = []

    monkeypatch.setattr(
        retrieval_cli,
        "plan_search_expressions",
        lambda _case, **_kwargs: ("student entity", "student names column"),
    )

    def fake_db_search(_session, _datasource_id: str, query: str, _limit: int):
        calls.append(query)
        if query == "student entity":
            return {
                "engine": "vector",
                "original_query": query,
                "retrieval_latency_ms": 5.0,
                "embedding_build_time_ms": 1.0,
                "vector_available": True,
                "results": [
                    {"type": "table", "table_name": "teachers", "score": 0.9},
                    {"type": "table", "table_name": "students", "score": 0.8},
                ],
            }
        return {
            "engine": "vector",
            "original_query": query,
            "retrieval_latency_ms": 7.0,
            "embedding_build_time_ms": 0.0,
            "vector_available": True,
            "results": [
                {"type": "column", "table_name": "students", "column_name": "name", "score": 0.95},
                {"type": "table", "table_name": "students", "score": 0.7},
            ],
        }

    monkeypatch.setattr(retrieval_cli, "db_search", fake_db_search)

    artifacts = retrieval_cli._run_ai_assisted_retrieval_case(
        db_session=object(),
        datasource_id="ds-tiny",
        case=case,
        limit=5,
        model="qwen-plus",
    )

    assert calls == ["student entity", "student names column"]
    assert [event["step"]["tool_name"] for event in artifacts.events] == [
        "search.plan",
        "db.search",
        "db.search",
        "db.search.fused",
    ]
    fused = artifacts.events[-1]["step"]["output"]
    assert fused["search_expressions"] == ["student entity", "student names column"]
    assert fused["db_search_call_count"] == 2
    assert [row["table_name"] for row in fused["results"][:2]] == ["students", "students"]
    assert fused["results"][0]["matched_by"] == ["multi_query", "vector"]


def test_write_reports_outputs_summary_json_cases_csv_and_markdown(tmp_path: Path) -> None:
    case = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_concert_singer_001",
            db_id="concert_singer",
            variant="keyword",
            question="Which singers performed in 2014?",
            expected_tables=("singer",),
            expected_columns=("singer.name",),
            retrieved_items=(
                RetrievalHit(type="table", table_name="singer", score=9.0),
                RetrievalHit(type="column", table_name="singer", column_name="name", score=8.0),
            ),
            actual_sql="SELECT singer.name FROM singer",
            query_execution_success=True,
            latency_ms=1000,
            retrieval_latency_ms=20.0,
            embedding_build_time_ms=3.0,
            vector_available=True,
            step_count=3,
            tool_call_count=2,
        )
    )
    summary = summarize_variant("keyword", (case,))

    paths = write_reports(
        output_dir=tmp_path,
        benchmark="spider",
        variants=("keyword",),
        summaries=(summary,),
        cases=(case,),
    )

    assert paths.summary_json.name == "spider_keyword_summary.json"
    summary_json = json.loads(paths.summary_json.read_text(encoding="utf-8"))
    assert summary_json["summaries"][0]["variant"] == "keyword"
    assert summary_json["summaries"][0]["failure_class_counts"] == {"none": 1}
    assert paths.cases_jsonl.name == "spider_keyword_cases.jsonl"
    jsonl_rows = [
        json.loads(line)
        for line in paths.cases_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert jsonl_rows[0]["failure_class"] == "none"
    csv_text = paths.cases_csv.read_text(encoding="utf-8")
    assert "case_id,db_id,variant,question" in csv_text
    assert "retrieval_latency_ms" in csv_text
    assert "embedding_build_time_ms" in csv_text
    assert "vector_available" in csv_text
    assert "failure_class" in csv_text
    assert "used_tables" in csv_text
    assert "spider_concert_singer_001" in csv_text
    md_text = paths.markdown_report.read_text(encoding="utf-8")
    assert "p95_retrieval_ms" in md_text
    assert "p95_embedding_ms" in md_text
    assert "Failure breakdown" in md_text
    assert "| keyword | 100.0% | 100.0% | 100.0% | 100.0% | 1000 | 20.0 | 3.0 | 3.0 | 0 |" in md_text


def test_cli_dry_run_writes_reports_without_calling_live_agent(tmp_path: Path, monkeypatch) -> None:
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

    monkeypatch.setattr(retrieval_cli, "_create_temp_metadata_session", lambda _path: FakeSession())
    monkeypatch.setattr(retrieval_cli, "create_dbfox_sqlite_run_fn", lambda **_kwargs: object())

    def fail_live_call(*_args, **_kwargs):
        raise AssertionError("dry run should not call live Agent")

    monkeypatch.setattr(retrieval_cli, "_run_live_case", fail_live_call)

    assert retrieval_cli.main(
        [
            "--benchmark",
            "spider",
            "--cases",
            str(cases_path),
            "--variants",
            "keyword",
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    ) == 0
    assert (tmp_path / "reports" / "spider_keyword_summary.json").exists()


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
    monkeypatch.setattr(retrieval_cli, "_load_examples_for_cases", lambda *_args, **_kwargs: (object(),))
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


def test_cli_ai_assisted_retrieval_reuses_plan_across_variants(tmp_path: Path, monkeypatch) -> None:
    cases_path = tmp_path / "dev.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "db_id": "tiny_school",
                    "question": "List all student names.",
                    "query": "SELECT name FROM students",
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

    plan_calls: list[str] = []
    search_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(retrieval_cli, "_create_temp_metadata_session", lambda _path: FakeSession())
    monkeypatch.setattr(retrieval_cli, "_load_examples_for_cases", lambda *_args, **_kwargs: (object(),))
    monkeypatch.setattr(
        retrieval_cli,
        "_ensure_spider_sqlite_datasource",
        lambda _session, _example: ("ds-tiny", ["students"]),
    )
    monkeypatch.setattr(retrieval_cli, "_prewarm_schema_embeddings_if_needed", lambda _session, _datasource_id: None)

    def fake_plan(case: EvaluationCase, **_kwargs):
        plan_calls.append(case.case_id)
        return ("student entity", "student names column")

    def fake_db_search(_session, _datasource_id: str, query: str, _limit: int):
        search_calls.append((os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"], query))
        return {
            "engine": os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"],
            "original_query": query,
            "retrieval_latency_ms": 1.0,
            "embedding_build_time_ms": 0.0,
            "vector_available": None,
            "results": [
                {"type": "table", "table_name": "students", "score": 1.0},
                {"type": "column", "table_name": "students", "column_name": "name", "score": 0.9},
            ],
        }

    monkeypatch.setattr(retrieval_cli, "plan_search_expressions", fake_plan)
    monkeypatch.setattr(retrieval_cli, "db_search", fake_db_search)

    assert retrieval_cli.main(
        [
            "--benchmark",
            "spider",
            "--cases",
            str(cases_path),
            "--variants",
            "keyword,vector,hybrid",
            "--mode",
            "ai-assisted-retrieval",
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    ) == 0

    assert plan_calls == ["spider_tiny_school_001"]
    assert search_calls == [
        ("keyword", "student entity"),
        ("keyword", "student names column"),
        ("vector", "student entity"),
        ("vector", "student names column"),
        ("hybrid", "student entity"),
        ("hybrid", "student names column"),
    ]
    csv_text = (tmp_path / "reports" / "spider_keyword_vector_hybrid_cases.csv").read_text(encoding="utf-8")
    assert "ai-assisted-retrieval" in csv_text
    assert "student names column" in csv_text


def test_cli_prewarm_embeddings_only_for_vector_and_hybrid(monkeypatch) -> None:
    calls: list[str] = []

    def fake_ensure(_db_session, datasource_id: str) -> None:
        calls.append(datasource_id)
        return type(
            "Build",
            (),
            {
                "embedding_build_time_ms": 2.5,
                "built_count": 1,
                "model": "fake",
                "dimension": 2,
            },
        )()

    monkeypatch.setattr(retrieval_cli, "ensure_schema_embeddings", fake_ensure)

    monkeypatch.setenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "keyword")
    keyword_event = retrieval_cli._prewarm_schema_embeddings_if_needed(object(), "ds-keyword")

    monkeypatch.setenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "vector")
    vector_event = retrieval_cli._prewarm_schema_embeddings_if_needed(object(), "ds-vector")

    monkeypatch.setenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "hybrid")
    hybrid_event = retrieval_cli._prewarm_schema_embeddings_if_needed(object(), "ds-hybrid")

    assert calls == ["ds-vector", "ds-hybrid"]
    assert keyword_event is None
    assert vector_event["step"]["tool_name"] == "schema.embedding.prewarm"
    assert vector_event["step"]["output"]["vector_available"] is True
    assert hybrid_event["step"]["output"]["embedding_build_time_ms"] == 2.5


def test_cli_disposes_temporary_metadata_engine(tmp_path: Path, monkeypatch) -> None:
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

    class FakeBind:
        def __init__(self) -> None:
            self.disposed = False

        def dispose(self) -> None:
            self.disposed = True

    class FakeSession:
        def __init__(self) -> None:
            self.bind = FakeBind()
            self.closed = False

        def close(self) -> None:
            self.closed = True

        def get_bind(self):
            return self.bind

    fake_session = FakeSession()
    monkeypatch.setattr(retrieval_cli, "_create_temp_metadata_session", lambda _path: fake_session)
    monkeypatch.setattr(retrieval_cli, "create_dbfox_sqlite_run_fn", lambda **_kwargs: object())

    assert retrieval_cli.main(
        [
            "--benchmark",
            "spider",
            "--cases",
            str(cases_path),
            "--variants",
            "keyword",
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    ) == 0
    assert fake_session.closed is True
    assert fake_session.bind.disposed is True


def test_cli_temp_metadata_session_uses_sqlite_wal_and_busy_timeout(tmp_path: Path) -> None:
    session = retrieval_cli._create_temp_metadata_session(tmp_path / "metadata.sqlite")
    try:
        rows = session.execute(sa_text("PRAGMA journal_mode")).fetchone()
        busy = session.execute(sa_text("PRAGMA busy_timeout")).fetchone()
        assert rows is not None
        assert rows[0].lower() == "wal"
        assert busy is not None
        assert int(busy[0]) >= 30000
    finally:
        retrieval_cli._close_metadata_session(session)


def test_cli_configures_eval_runtime_to_disable_query_history(monkeypatch) -> None:
    monkeypatch.delenv("DBFOX_DISABLE_QUERY_HISTORY", raising=False)

    retrieval_cli._configure_eval_runtime_env()

    assert os.environ["DBFOX_DISABLE_QUERY_HISTORY"] == "1"
