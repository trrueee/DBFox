from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import engine.evaluation.benchmarks.bird as bird_benchmark
import engine.evaluation.benchmarks.custom as custom_benchmark
import engine.evaluation.benchmarks.spider as spider_benchmark
import engine.evaluation.langsmith_adapter as langsmith_adapter
import engine.evaluation.spider.spider_eval as spider_eval
import engine.evaluation.spider.sql_result_comparator as sql_result_comparator
from engine.agent_core.types import AgentRunResponse
from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.evaluation.agent_case_evaluator import AgentCaseEvaluator
from engine.evaluation.benchmarks.bird import BIRDAdapter
from engine.evaluation.benchmarks.custom import CustomAdapter
from engine.evaluation.benchmarks.spider import SpiderAdapter
from engine.evaluation.spider.spider_eval import SpiderEvalRunner
from engine.evaluation.spider.spider_loader import SpiderExample
from engine.models import AgentGoldenTask, GoldenSQL
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


SENTINEL = "evaluation-provider-secret-sentinel"


def _isolated_capture_logger(caplog: pytest.LogCaptureFixture, name: str, level: int) -> logging.Logger:
    logger = logging.Logger(name)
    logger.setLevel(level)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    return logger


def _spider_example() -> SpiderExample:
    return SpiderExample(
        db_id="boundary",
        question="select a value",
        gold_sql="SELECT 1",
        db_path=Path("unused-boundary.sqlite"),
    )


def _agent_task(datasource_id: str, question: str) -> AgentGoldenTask:
    return AgentGoldenTask(
        datasource_id=datasource_id,
        name="evaluation-boundary",
        question=question,
        workspace_context_json="{}",
        expected_intent=None,
        expected_tools_json="[]",
        forbidden_tools_json="[]",
        expected_artifact_types_json="[]",
        expected_final_contains_json="[]",
        expected_approval_state=None,
        expected_sql_required=False,
        tags_json="[]",
        source="internal",
    )


@pytest.mark.parametrize(
    ("raises", "expected_code"),
    [
        (False, FixedErrorCode.SQL_EXECUTION_FAILED),
        (True, FixedErrorCode.EVAL_RUN_ERROR),
    ],
)
def test_agent_case_evaluation_never_serializes_executor_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Any,
    test_datasource: Any,
    raises: bool,
    expected_code: FixedErrorCode,
) -> None:
    from engine.sql.dialect_context import DialectContext
    from engine.sql.safety.service import SqlSafetyService

    question = "evaluation boundary golden SQL"
    db_session.add(
        GoldenSQL(
            data_source_id=test_datasource.id,
            question=question,
            golden_sql="SELECT 1",
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        DialectContext,
        "from_datasource_id",
        staticmethod(lambda *_args: object()),
    )
    monkeypatch.setattr(
        SqlSafetyService,
        "build_execution_decision",
        lambda *_args, **_kwargs: object(),
    )

    def fake_execute_query(_db: Any, _datasource_id: str, sql: str, **_kwargs: Any) -> dict[str, Any]:
        if sql == "SELECT 1":
            return {"success": True, "rows": []}
        if raises:
            raise RuntimeError(f"database password={SENTINEL}")
        return {"success": False, "error": f"database password={SENTINEL}"}

    monkeypatch.setattr("engine.sql.executor.execute_query", fake_execute_query)

    evaluation = AgentCaseEvaluator(db=db_session).evaluate(
        _agent_task(test_datasource.id, question),
        AgentRunResponse(
            run_id="run-evaluation-boundary",
            session_id="session-evaluation-boundary",
            success=True,
            status="success",
            question=question,
            sql="SELECT 2",
        ),
    )

    persisted_shape = evaluation.model_dump_json()
    assert expected_code.value in evaluation.failure_reasons
    assert SENTINEL not in persisted_shape


def test_spider_sql_comparator_never_returns_driver_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_connect(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.OperationalError(f"database password={SENTINEL}")

    monkeypatch.setattr(sql_result_comparator.sqlite3, "connect", failing_connect)

    result = sql_result_comparator.execute_sqlite_query("unused.sqlite", "SELECT 1")

    assert result.error == fixed_error_message(FixedErrorCode.SQL_EXECUTION_FAILED)
    assert SENTINEL not in json.dumps(result.__dict__)


def test_spider_runner_masks_run_exception_in_result_and_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failing_run(_example: SpiderExample) -> tuple[Any, list[dict[str, Any]], int]:
        raise RuntimeError(f"provider token={SENTINEL}")

    logger = _isolated_capture_logger(caplog, "test.spider_runner_error_boundary", logging.ERROR)
    try:
        monkeypatch.setattr(spider_eval, "logger", logger)
        result = SpiderEvalRunner(run_fn=failing_run).run_example(_spider_example())
    finally:
        logger.removeHandler(caplog.handler)

    assert result.error == fixed_error_message(FixedErrorCode.EVAL_RUN_ERROR)
    assert SENTINEL not in json.dumps(result.__dict__)
    assert SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_eval_run" in caplog.text


def test_dbfox_spider_runtime_failure_uses_fixed_event_payload(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import engine.agent as agent_module

    class FailingRuntime:
        def __init__(self, _db: Any) -> None:
            pass

        def run_iter(self, _request: Any):
            raise RuntimeError(f"provider token={SENTINEL}")
            yield None

    monkeypatch.setattr(
        spider_eval,
        "_ensure_spider_sqlite_datasource",
        lambda *_args: ("datasource-boundary", ["records"]),
    )
    monkeypatch.setattr(agent_module, "DBFoxAgentRuntime", FailingRuntime)
    logger = _isolated_capture_logger(caplog, "test.spider_runtime_event_boundary", logging.ERROR)
    try:
        monkeypatch.setattr(spider_eval, "logger", logger)
        _response, events, _latency, _datasource_id, _tables = spider_eval.create_dbfox_sqlite_run_fn(
            db_session=object(),
            llm_credential_id="cred_llm_api_key_boundary",
        )(_spider_example())
    finally:
        logger.removeHandler(caplog.handler)

    event_step = events[-1]["step"]
    assert event_step["error"] == fixed_error_message(FixedErrorCode.EVAL_RUN_ERROR)
    assert event_step["error_code"] == FixedErrorCode.EVAL_RUN_ERROR.value
    assert SENTINEL not in json.dumps(events)
    assert SENTINEL not in caplog.text


def test_qwen_spider_runtime_failure_uses_fixed_event_payload(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import httpx

    def failing_post(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(f"provider token={SENTINEL}")

    monkeypatch.setattr(httpx, "post", failing_post)
    logger = _isolated_capture_logger(caplog, "test.spider_qwen_event_boundary", logging.ERROR)
    try:
        monkeypatch.setattr(spider_eval, "logger", logger)
        _response, events, _latency = spider_eval.create_qwen_text_to_sql_baseline_run_fn(
            api_key="test-key",
        )(_spider_example())
    finally:
        logger.removeHandler(caplog.handler)

    event_step = events[-1]["step"]
    assert event_step["error"] == fixed_error_message(FixedErrorCode.EVAL_RUN_ERROR)
    assert event_step["error_code"] == FixedErrorCode.EVAL_RUN_ERROR.value
    assert SENTINEL not in json.dumps(events)
    assert SENTINEL not in caplog.text


@pytest.mark.parametrize(
    ("benchmark_module", "adapter_type"),
    [
        (bird_benchmark, BIRDAdapter),
        (custom_benchmark, CustomAdapter),
        (spider_benchmark, SpiderAdapter),
    ],
)
def test_benchmark_import_logs_never_include_parser_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    benchmark_module: ModuleType,
    adapter_type: type[Any],
) -> None:
    path = tmp_path / "benchmark.json"
    path.write_text("{}", encoding="utf-8")

    def failing_read_text(*_args: Any, **_kwargs: Any) -> str:
        raise OSError(f"provider token={SENTINEL}")

    logger = _isolated_capture_logger(caplog, "test.benchmark_import_boundary", logging.WARNING)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(benchmark_module, "logger", logger)
            scoped_monkeypatch.setattr(benchmark_module.Path, "read_text", failing_read_text)
            assert adapter_type().load_cases(path=str(path)) == []
    finally:
        logger.removeHandler(caplog.handler)

    assert SENTINEL not in caplog.text
    assert "OSError" in caplog.text
    assert "agent_eval_benchmark_import" in caplog.text


def test_langsmith_sync_log_never_includes_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def create_dataset(self, _dataset_name: str) -> None:
            raise RuntimeError(f"provider token={SENTINEL}")

        def list_datasets(self, **_kwargs: Any) -> list[Any]:
            raise RuntimeError(f"provider token={SENTINEL}")

    fake_langsmith = ModuleType("langsmith")
    fake_langsmith.Client = FailingClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.LANGSMITH_API_KEY,
        secret="langsmith-test-secret",
    )
    adapter = langsmith_adapter.LangSmithAdapter(
        credential_id=credential_id,
        credential_vault=vault,
    )
    logger = _isolated_capture_logger(caplog, "test.langsmith_error_boundary", logging.WARNING)
    try:
        monkeypatch.setattr(langsmith_adapter, "logger", logger)
        adapter.sync_dataset("boundary-dataset", [])
    finally:
        logger.removeHandler(caplog.handler)

    assert SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "agent_eval_run" in caplog.text
