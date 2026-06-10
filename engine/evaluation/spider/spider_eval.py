from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from engine.evaluation.spider.spider_loader import SpiderExample, load_spider_examples
from engine.evaluation.spider.sql_prediction_extractor import extract_final_sql
from engine.evaluation.spider.sql_result_comparator import compare_sqlite_execution

logger = logging.getLogger("databox.spider_eval")


@dataclass
class SpiderCaseResult:
    db_id: str
    question: str
    gold_sql: str
    predicted_sql: str | None
    generated_sql: bool
    execution_success: bool
    execution_match: bool
    latency_ms: int
    error: str | None = None
    gold_rows_count: int | None = None
    predicted_rows_count: int | None = None
    tool_sequence: list[str] | None = None
    datasource_id: str | None = None
    synced_table_names: list[str] | None = None
    generation_metadata: dict[str, Any] | None = None


@dataclass
class SpiderEvalSummary:
    total_cases: int
    generated_sql_cases: int
    execution_success_cases: int
    execution_match_cases: int
    generated_sql_rate: float
    execution_success_rate: float
    execution_accuracy: float
    avg_latency_ms: float | None
    runner_mode: str = "unknown"
    is_databox_score: bool = False


def _extract_tool_sequence(events: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for event in events:
        step = event.get("step")
        if isinstance(step, dict):
            tool = step.get("tool_name") or step.get("name")
            if isinstance(tool, str) and tool and tool not in tools:
                tools.append(tool)
    return tools


def _extract_generation_metadata(response: Any, events: list[dict[str, Any]]) -> dict[str, Any] | None:
    safety = getattr(response, "safety", None)
    if isinstance(safety, dict) and isinstance(safety.get("generation_metadata"), dict):
        return dict(safety["generation_metadata"])
    for event in reversed(events):
        step = event.get("step")
        if isinstance(step, dict):
            output = step.get("output")
            if isinstance(output, dict) and isinstance(output.get("metadata"), dict):
                return dict(output["metadata"])
            if isinstance(output, dict) and isinstance(output.get("generation_metadata"), dict):
                return dict(output["generation_metadata"])
        event_response = event.get("response")
        if isinstance(event_response, dict):
            event_safety = event_response.get("safety")
            if isinstance(event_safety, dict) and isinstance(event_safety.get("generation_metadata"), dict):
                return dict(event_safety["generation_metadata"])
    return None


def classify_failure(result: SpiderCaseResult) -> str | None:
    if not result.generated_sql:
        return "no_predicted_sql"
    if not result.execution_success:
        return "predicted_sql_execution_error"
    if not result.execution_match:
        return "execution_result_mismatch"
    return None


def summarize_spider_results(
    results: list[SpiderCaseResult],
    *,
    runner_mode: str = "unknown",
    is_databox_score: bool = False,
) -> SpiderEvalSummary:
    total = len(results)
    generated = sum(1 for r in results if r.generated_sql)
    execution_success = sum(1 for r in results if r.execution_success)
    execution_match = sum(1 for r in results if r.execution_match)
    total_latency = sum(r.latency_ms for r in results)

    return SpiderEvalSummary(
        total_cases=total,
        generated_sql_cases=generated,
        execution_success_cases=execution_success,
        execution_match_cases=execution_match,
        generated_sql_rate=round(generated / max(total, 1), 4),
        execution_success_rate=round(execution_success / max(total, 1), 4),
        execution_accuracy=round(execution_match / max(total, 1), 4),
        avg_latency_ms=round(total_latency / total, 2) if total else None,
        runner_mode=runner_mode,
        is_databox_score=is_databox_score,
    )


class SpiderEvalRunner:
    """Runner for Spider evaluation with pluggable runtime backend.

    The *run_fn* callable takes a SpiderExample and returns
    ``(response, events_payload, latency_ms)``.  This keeps the runner
    agnostic to whether DataBox is wired or a fake is used for testing.
    """

    def __init__(
        self,
        run_fn: Any = None,
        *,
        execute: bool = True,
        runner_mode: str = "unknown",
    ) -> None:
        self._run_fn = run_fn
        self.execute = execute
        self._runner_mode = runner_mode

    def run_example(self, example: SpiderExample) -> SpiderCaseResult:
        response = None
        events_payload: list[dict[str, Any]] = []
        latency_ms = 0
        error: str | None = None
        datasource_id: str | None = None
        synced_table_names: list[str] | None = None

        try:
            if self._run_fn is not None:
                result = self._run_fn(example)
                if len(result) == 5:
                    response, events_payload, latency_ms, datasource_id, synced_table_names = result
                else:
                    response, events_payload, latency_ms = result
            else:
                return SpiderCaseResult(
                    db_id=example.db_id, question=example.question,
                    gold_sql=example.gold_sql, predicted_sql=None,
                    generated_sql=False, execution_success=False,
                    execution_match=False, latency_ms=0,
                    error="No run_fn configured.",
                )
        except Exception as exc:
            error = str(exc)

        if error:
            return SpiderCaseResult(
                db_id=example.db_id, question=example.question,
                gold_sql=example.gold_sql, predicted_sql=None,
                generated_sql=False, execution_success=False,
                execution_match=False, latency_ms=latency_ms,
                error=error,
                tool_sequence=_extract_tool_sequence(events_payload),
                datasource_id=datasource_id,
                synced_table_names=synced_table_names,
            )

        predicted_sql = extract_final_sql(response, events_payload)
        generation_metadata = _extract_generation_metadata(response, events_payload)
        if not predicted_sql:
            return SpiderCaseResult(
                db_id=example.db_id, question=example.question,
                gold_sql=example.gold_sql, predicted_sql=None,
                generated_sql=False, execution_success=False,
                execution_match=False, latency_ms=latency_ms,
                error="No predicted SQL.",
                tool_sequence=_extract_tool_sequence(events_payload),
                datasource_id=datasource_id,
                synced_table_names=synced_table_names,
                generation_metadata=generation_metadata,
            )

        if self.execute:
            comparison = compare_sqlite_execution(example.db_path, example.gold_sql, predicted_sql)
            return SpiderCaseResult(
                db_id=example.db_id, question=example.question,
                gold_sql=example.gold_sql, predicted_sql=predicted_sql,
                generated_sql=True,
                execution_success=comparison.predicted_success,
                execution_match=comparison.execution_match,
                latency_ms=latency_ms,
                error=comparison.predicted_error,
                gold_rows_count=comparison.gold_rows_count,
                predicted_rows_count=comparison.predicted_rows_count,
                tool_sequence=_extract_tool_sequence(events_payload),
                datasource_id=datasource_id,
                synced_table_names=synced_table_names,
                generation_metadata=generation_metadata,
            )

        return SpiderCaseResult(
            db_id=example.db_id, question=example.question,
            gold_sql=example.gold_sql, predicted_sql=predicted_sql,
            generated_sql=True, execution_success=False,
            execution_match=False, latency_ms=latency_ms,
            error=None,
            tool_sequence=_extract_tool_sequence(events_payload),
            datasource_id=datasource_id,
            synced_table_names=synced_table_names,
            generation_metadata=generation_metadata,
        )

    def run(
        self,
        spider_root: str | Path,
        *,
        split: str = "dev",
        limit: int | None = None,
        db_ids: set[str] | None = None,
    ) -> tuple[list[SpiderCaseResult], SpiderEvalSummary]:
        examples = load_spider_examples(spider_root, split=split, limit=limit, db_ids=db_ids)
        results = [self.run_example(ex) for ex in examples]
        is_databox = self._runner_mode == "databox"
        summary = summarize_spider_results(results, runner_mode=self._runner_mode, is_databox_score=is_databox)
        return results, summary


# -- DataBox runtime integration ---------------------------------------------


def create_databox_sqlite_run_fn(
    *,
    db_session: Any,
    api_key: str | None = None,
    api_base: str | None = None,
    model_name: str | None = None,
    execute: bool = True,
    max_steps: int = 20,
) -> Any:
    """Return a run_fn backed by DataBoxAgentRuntime for Spider SQLite DBs.

    *db_session* must be an active SQLAlchemy Session pointing to DataBox's
    own metadata database (the one holding data_sources, schema_tables, etc.).

    Returns a 5-tuple: (response, events, latency_ms, datasource_id, synced_table_names).
    """

    def _run(example: SpiderExample) -> tuple[Any, list[dict[str, Any]], int, str, list[str]]:
        import time as _time
        start = _time.monotonic()

        datasource_id, synced_tables = _ensure_spider_sqlite_datasource(db_session, example)

        from engine.agent_core.runtime import DataBoxAgentRuntime
        from engine.agent_core.types import AgentRunRequest

        runtime = DataBoxAgentRuntime(db_session)
        events_payload: list[dict[str, Any]] = []
        response = None

        req = AgentRunRequest(
            datasource_id=datasource_id,
            question=example.question,
            execute=execute,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            max_steps=max_steps,
        )

        try:
            for event in runtime.run_iter(req):
                payload = event.model_dump(mode="json")
                events_payload.append(payload)
                if event.response is not None:
                    response = event.response
        except Exception as exc:
            events_payload.append({"step": {"error": str(exc)}})

        latency = int((_time.monotonic() - start) * 1000)
        return response, events_payload, latency, datasource_id, synced_tables

    return _run


def _ensure_spider_sqlite_datasource(db_session: Any, example: SpiderExample) -> tuple[str, list[str]]:
    """Create or retrieve a DataSource row for a Spider SQLite database.

    Returns (datasource_id, synced_table_names).  Raises RuntimeError if
    schema sync fails or produces zero tables.
    """
    import uuid
    from engine.models import DataSource

    db_path = str(example.db_path.resolve())

    existing = (
        db_session.query(DataSource)
        .filter(DataSource.host == "spider", DataSource.database_name == db_path)
        .first()
    )
    if existing is not None:
        if existing.last_sync_status != "success":
            _sync_and_validate(db_session, str(existing.id))
        tables = _get_synced_table_names(db_session, str(existing.id))
        return str(existing.id), tables

    ds_id = f"spider_{example.db_id}_{uuid.uuid4().hex[:8]}"
    ds = DataSource(
        id=ds_id,
        name=f"Spider {example.db_id}",
        db_type="sqlite",
        host="spider",
        port=0,
        database_name=db_path,
        username="",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    _sync_and_validate(db_session, ds_id)
    tables = _get_synced_table_names(db_session, ds_id)
    return ds_id, tables


def _sync_and_validate(db_session: Any, datasource_id: str) -> None:
    """Sync schema and raise if it fails."""
    from engine.schema_sync import sync_schema

    sync_schema(db_session, datasource_id)

    tables = _get_synced_table_names(db_session, datasource_id)
    if not tables:
        raise RuntimeError(
            f"Spider datasource {datasource_id} synced zero schema tables. "
            f"Check that the SQLite database exists and has tables."
        )


def _get_synced_table_names(db_session: Any, datasource_id: str) -> list[str]:
    from engine.models import SchemaTable

    rows = (
        db_session.query(SchemaTable.table_name)
        .filter(SchemaTable.data_source_id == datasource_id)
        .all()
    )
    return sorted([r[0] for r in rows])


# -- Qwen direct baseline ----------------------------------------------------


def create_qwen_text_to_sql_baseline_run_fn(
    *,
    api_key: str,
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name: str = "qwen-plus",
) -> Any:
    """Return a run_fn that calls Qwen directly for Text-to-SQL.

    This bypasses DataBox runtime — it sends the question directly to the
    LLM and returns the generated SQL.  Execution comparison still goes
    through Spider's SQLite comparator.
    Only use this as a baseline, NOT as a DataBox score.
    """
    import httpx

    def _run(example: SpiderExample) -> tuple[Any, list[dict[str, Any]], int]:
        import time as _time
        start = _time.monotonic()

        prompt = (
            "You are a Text-to-SQL assistant. Given a natural language question, "
            "generate a single SQLite-compatible SELECT statement.\n"
            "Return ONLY the SQL statement, no explanation, no markdown.\n\n"
            f"Question: {example.question}\nSQL:"
        )

        sql = None
        error = None
        try:
            resp = httpx.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "You are a Text-to-SQL generator. Output only SQL, no explanation."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            for prefix in ("```sql", "```"):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):].strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()
            sql = raw if raw else None
        except Exception as exc:
            error = str(exc)

        latency = int((_time.monotonic() - start) * 1000)

        class _FakeResponse:
            pass
        response = _FakeResponse()
        response.sql = sql  # type: ignore

        events = [
            {"step": {"name": "generate_sql_candidate", "tool_name": "sql.generate", "sql": sql or "", "output": {"sql": sql or ""}}},
        ]
        if error:
            events.append({"step": {"name": "generate_sql_candidate", "tool_name": "sql.generate", "error": error}})

        return response, events, latency

    return _run


# -- CLI --------------------------------------------------------------------


def _cli() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="DataBox Spider Eval Runner")
    parser.add_argument("--spider-root", required=True, help="Path to Spider dataset root")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--db-id", default=None)
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--output", default=None, help="Write JSON results to file")
    parser.add_argument(
        "--mode",
        default="fake",
        choices=["fake", "databox", "qwen-baseline"],
        help="Runner mode (default: fake for testing)",
    )
    args = parser.parse_args()

    db_ids = {args.db_id} if args.db_id else None

    if args.mode == "databox":
        _run_databox_cli(args, db_ids)
    elif args.mode == "qwen-baseline":
        _run_qwen_baseline_cli(args, db_ids)
    else:
        _run_fake_cli(args, db_ids)


def _run_fake_cli(args: Any, db_ids: set[str] | None) -> None:
    runner = SpiderEvalRunner(execute=args.execute, runner_mode="fake")
    results, summary = runner.run(args.spider_root, split=args.split, limit=args.limit, db_ids=db_ids)
    _write_output(results, summary, args.output)


def _run_qwen_baseline_cli(args: Any, db_ids: set[str] | None) -> None:
    import os as _os
    api_key = args.api_key or _os.environ.get("DATABOX_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("--api-key required for qwen-baseline mode")
    run_fn = create_qwen_text_to_sql_baseline_run_fn(
        api_key=api_key,
        api_base=args.api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_name=args.model_name or "qwen-plus",
    )
    runner = SpiderEvalRunner(run_fn=run_fn, execute=args.execute, runner_mode="qwen-baseline")
    results, summary = runner.run(args.spider_root, split=args.split, limit=args.limit, db_ids=db_ids)
    _write_output(results, summary, args.output)


def _run_databox_cli(args: Any, db_ids: set[str] | None) -> None:
    import os as _os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from engine.db import Base
    from engine import models  # noqa: F401  # register models

    api_key = args.api_key or _os.environ.get("DATABOX_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("--api-key or DATABOX_LLM_API_KEY required for databox mode")

    # In-memory metadata DB (isolated from production databox_local.db)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()

    try:
        run_fn = create_databox_sqlite_run_fn(
            db_session=db_session,
            api_key=api_key,
            api_base=args.api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model_name=args.model_name or "qwen-plus",
            execute=args.execute,
        )
        runner = SpiderEvalRunner(run_fn=run_fn, execute=args.execute, runner_mode="databox")
        results, summary = runner.run(args.spider_root, split=args.split, limit=args.limit, db_ids=db_ids)
        _write_output(results, summary, args.output)
    finally:
        db_session.close()


def _write_output(
    results: list[SpiderCaseResult],
    summary: SpiderEvalSummary,
    output_path: str | None,
) -> None:
    output = {
        "summary": asdict(summary),
        "cases": [asdict(r) for r in results],
    }
    if output_path and output_path != "-":
        Path(output_path).write_text(
            json.dumps(output, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"Wrote {len(results)} cases to {output_path}")

    print(
        f"total={summary.total_cases} "
        f"gen_sql={summary.generated_sql_rate:.2%} "
        f"exec_success={summary.execution_success_rate:.2%} "
        f"exec_acc={summary.execution_accuracy:.2%} "
        f"mode={summary.runner_mode} "
        f"is_databox={summary.is_databox_score}"
    )


if __name__ == "__main__":
    _cli()
