from __future__ import annotations

import argparse
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session, sessionmaker

from engine.db import Base
from engine.evaluation.retrieval_ab.config import DEFAULT_ENV_FILE, RetrievalAbConfig, load_env_file
from engine.evaluation.retrieval_ab.query_planner import plan_search_expressions
from engine.evaluation.retrieval_ab.report import write_reports
from engine.evaluation.retrieval_ab.runner import AgentRunArtifacts, evaluate_artifacts
from engine.evaluation.retrieval_ab.spider_fixture import load_spider_cases
from engine.evaluation.spider.spider_eval import _ensure_spider_sqlite_datasource, create_dbfox_sqlite_run_fn
from engine.evaluation.spider.spider_loader import SpiderExample, load_spider_examples
from engine.evaluation.spider.sql_prediction_extractor import extract_final_sql
from engine.evaluation.spider.sql_result_comparator import compare_sqlite_execution
from engine.tools.db.embedding import ensure_schema_embeddings
from engine.tools.db.search import db_search


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    load_env_file(os.getenv("DBFOX_EVAL_ENV_FILE") or DEFAULT_ENV_FILE)
    _configure_eval_runtime_env()
    cfg = RetrievalAbConfig.from_mapping(vars(args))
    if cfg.benchmark != "spider":
        raise ValueError("Only the spider benchmark is supported in Phase 0.")

    cases = load_spider_cases(cfg.cases_path, db_ids=cfg.db_ids, limit=args.limit)
    examples = _load_examples_for_cases(cfg.cases_path, db_ids=cfg.db_ids, limit=args.limit)
    if len(cases) != len(examples):
        raise RuntimeError(f"Loaded {len(cases)} cases but {len(examples)} Spider examples.")

    results = []
    search_expression_cache: dict[str, tuple[str, ...]] = {}
    with tempfile.TemporaryDirectory(prefix="dbfox-retrieval-ab-") as tmp:
        db_session = _create_temp_metadata_session(Path(tmp) / "dbfox_eval.sqlite")
        try:
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
                    elif cfg.mode == "ai-assisted-retrieval":
                        datasource_id, _synced_tables = _ensure_spider_sqlite_datasource(db_session, example)
                        prewarm_event = _prewarm_schema_embeddings_if_needed(db_session, datasource_id)
                        search_expressions = search_expression_cache.get(case.case_id)
                        if search_expressions is None:
                            search_expressions = plan_search_expressions(case, model=cfg.model)
                            search_expression_cache[case.case_id] = search_expressions
                        artifacts = _run_ai_assisted_retrieval_case(
                            db_session=db_session,
                            datasource_id=datasource_id,
                            case=case,
                            limit=cfg.retrieval_top_k,
                            model=cfg.model,
                            search_expressions=search_expressions,
                            pre_events=_event_tuple(prewarm_event),
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
        finally:
            _close_metadata_session(db_session)

    from engine.evaluation.retrieval_ab.metrics import summarize_variant

    summaries = tuple(
        summarize_variant(variant, (row for row in results if row.variant == variant))
        for variant in cfg.variants
    )
    paths = write_reports(
        output_dir=cfg.report_dir,
        benchmark=cfg.benchmark,
        variants=cfg.variants,
        summaries=summaries,
        cases=tuple(results),
    )
    print(f"summary: {paths.summary_json}")
    print(f"cases: {paths.cases_csv}")
    print(f"report: {paths.markdown_report}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DBFox retrieval A/B/n evaluation.")
    parser.add_argument("--benchmark", default="spider")
    parser.add_argument("--cases", default=None)
    parser.add_argument("--dbs", default="")
    parser.add_argument("--variants", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--mode", choices=("live", "retrieval-only", "ai-assisted-retrieval"), default=None)
    parser.add_argument("--report-dir", default="reports/retrieval_ab")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def _load_examples_for_cases(
    cases_path: Path,
    *,
    db_ids: tuple[str, ...],
    limit: int | None,
) -> tuple[SpiderExample, ...]:
    path = Path(cases_path)
    if path.suffix.lower() == ".json":
        root = path.parent
        split = path.stem
    else:
        root = path
        split = "dev"
    return tuple(load_spider_examples(root, split=split, limit=limit, db_ids=set(db_ids) or None))


def _run_live_case(run_fn: object, example: SpiderExample, *, execute: bool) -> AgentRunArtifacts:
    response = None
    events = []
    latency_ms = 0
    error = None
    try:
        response, events, latency_ms, _datasource_id, _synced_tables = run_fn(example)  # type: ignore[misc]
    except Exception as exc:
        error = str(exc)
    actual_sql = extract_final_sql(response, events)
    query_success = False
    if execute and actual_sql:
        comparison = compare_sqlite_execution(example.db_path, example.gold_sql, actual_sql)
        query_success = comparison.predicted_success
        error = error or comparison.predicted_error
    elif actual_sql:
        query_success = True
    return AgentRunArtifacts(
        actual_sql=actual_sql,
        query_execution_success=query_success,
        events=tuple(events),
        latency_ms=latency_ms,
        error=error,
    )


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


def _run_ai_assisted_retrieval_case(
    *,
    db_session: Session,
    datasource_id: str,
    vector_datasource_id: str | None = None,
    case: Any,
    limit: int,
    model: str | None = None,
    search_expressions: tuple[str, ...] | None = None,
    query_policy: str = "multi_keyword_vector_expression_each",
    pre_events: tuple[dict[str, Any], ...] = (),
) -> AgentRunArtifacts:
    started = time.perf_counter()
    expressions = search_expressions or plan_search_expressions(case, model=model)
    active_mode = os.getenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "keyword").strip().lower() or "keyword"
    events: list[dict[str, Any]] = list(pre_events)
    events.append(
        {
            "step": {
                "tool_name": "search.plan",
                "output": {
                    "search_expressions": list(expressions),
                    "query_policy": query_policy,
                    "planner_model": model,
                },
            }
        }
    )

    search_outputs: list[dict[str, Any]] = []
    if active_mode == "hybrid" and query_policy == "multi_keyword_vector_question":
        keyword_expressions = expressions
        vector_expressions = (case.question,)
        for expression in keyword_expressions:
            output = _db_search_with_mode(db_session, datasource_id, expression, limit, mode="keyword")
            search_outputs.append(
                {
                    "query": expression,
                    "output": output,
                    "retrieval_leg": "keyword",
                    "embedding_source": "none",
                }
            )
            events.append(
                {
                    "step": {
                        "tool_name": "db.search",
                        "input": {
                            "query": expression,
                            "limit": limit,
                            "datasource_id": datasource_id,
                            "retrieval_leg": "keyword",
                        },
                        "output": output,
                    }
                }
            )
        vector_ds = vector_datasource_id or datasource_id
        for expression in vector_expressions:
            output = _db_search_with_mode(db_session, vector_ds, expression, limit, mode="vector")
            search_outputs.append(
                {
                    "query": expression,
                    "output": output,
                    "retrieval_leg": "vector",
                    "embedding_source": "question",
                }
            )
            events.append(
                {
                    "step": {
                        "tool_name": "db.search",
                        "input": {
                            "query": expression,
                            "limit": limit,
                            "datasource_id": vector_ds,
                            "retrieval_leg": "vector",
                        },
                        "output": output,
                    }
                }
            )
    else:
        for expression in expressions:
            output = db_search(db_session, datasource_id, expression, limit)
            search_outputs.append(
                {
                    "query": expression,
                    "output": output,
                    "retrieval_leg": active_mode,
                    "embedding_source": _embedding_source_for_search(active_mode, expression, case.question),
                }
            )
            events.append(
                {
                    "step": {
                        "tool_name": "db.search",
                        "input": {
                            "query": expression,
                            "limit": limit,
                            "datasource_id": datasource_id,
                            "retrieval_leg": active_mode,
                        },
                        "output": output,
                    }
                }
            )

    if active_mode == "keyword":
        keyword_expressions_for_fuse = expressions
        vector_expressions_for_fuse: tuple[str, ...] = ()
    elif active_mode == "vector":
        keyword_expressions_for_fuse = ()
        vector_expressions_for_fuse = expressions
    elif active_mode == "hybrid" and query_policy == "multi_keyword_vector_question":
        keyword_expressions_for_fuse = expressions
        vector_expressions_for_fuse = (case.question,)
    else:
        keyword_expressions_for_fuse = expressions
        vector_expressions_for_fuse = expressions

    fused_output = fuse_multi_query_search_outputs(
        search_outputs,
        original_query=case.question,
        limit=limit,
        query_policy=query_policy,
        keyword_expressions=keyword_expressions_for_fuse,
        vector_expressions=vector_expressions_for_fuse,
    )
    events.append({"step": {"tool_name": "db.search.fused", "output": fused_output}})
    latency_ms = int(round((time.perf_counter() - started) * 1000))
    error = str(fused_output.get("error")) if fused_output.get("error") else None
    return AgentRunArtifacts(
        actual_sql=None,
        query_execution_success=False,
        events=tuple(events),
        latency_ms=latency_ms,
        error=error,
    )


def _db_search_with_mode(db_session: Session, datasource_id: str, query: str, limit: int, *, mode: str) -> dict[str, Any]:
    previous_mode = os.environ.get("DBFOX_SCHEMA_RETRIEVAL_MODE")
    try:
        os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = mode
        return db_search(db_session, datasource_id, query, limit)
    finally:
        if previous_mode is None:
            os.environ.pop("DBFOX_SCHEMA_RETRIEVAL_MODE", None)
        else:
            os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = previous_mode


def _embedding_source_for_search(mode: str, expression: str, original_query: str) -> str:
    if mode not in {"vector", "hybrid"}:
        return "none"
    if expression.strip() == str(original_query or "").strip():
        return "question"
    return "expression"


def fuse_multi_query_search_outputs(
    search_outputs: Sequence[dict[str, Any]],
    *,
    original_query: str,
    limit: int,
    rrf_k: int = 60,
    query_policy: str = "multi_keyword_vector_expression_each",
    keyword_expressions: Sequence[str] | None = None,
    vector_expressions: Sequence[str] | None = None,
) -> dict[str, Any]:
    expressions = [str(item.get("query") or "").strip() for item in search_outputs if str(item.get("query") or "").strip()]
    keyword_expression_list = [str(item).strip() for item in (keyword_expressions or expressions) if str(item).strip()]
    vector_expression_list = [str(item).strip() for item in (vector_expressions or expressions) if str(item).strip()]
    fused: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    vector_values: list[bool] = []
    errors: list[str] = []
    retrieval_latency_ms = 0.0
    embedding_build_time_ms = 0.0
    keyword_recall_ms = 0.0
    query_embedding_ms = 0.0
    question_embedding_ms = 0.0
    expression_embedding_ms = 0.0
    question_embedding_call_count = 0
    expression_embedding_call_count = 0
    vector_recall_ms = 0.0
    child_merge_ms = 0.0
    retrieval_only_ms = 0.0

    merge_started = time.perf_counter()
    for query_index, item in enumerate(search_outputs, start=1):
        output = item.get("output")
        if not isinstance(output, dict):
            continue
        retrieval_latency_ms += _float_value(output.get("retrieval_latency_ms"))
        embedding_build_time_ms += _float_value(output.get("embedding_build_time_ms"))
        keyword_recall_ms += _float_value(output.get("keyword_recall_ms"))
        child_query_embedding_ms = _float_value(output.get("query_embedding_ms"))
        query_embedding_ms += child_query_embedding_ms
        embedding_source = str(item.get("embedding_source") or "none")
        if embedding_source == "question":
            question_embedding_ms += child_query_embedding_ms
            question_embedding_call_count += 1
        elif embedding_source == "expression":
            expression_embedding_ms += child_query_embedding_ms
            expression_embedding_call_count += 1
        vector_recall_ms += _float_value(output.get("vector_recall_ms"))
        child_merge_ms += _float_value(output.get("merge_ms"))
        retrieval_only_ms += _float_value(output.get("retrieval_only_ms") or output.get("retrieval_latency_ms"))
        vector_available = output.get("vector_available")
        if isinstance(vector_available, bool):
            vector_values.append(vector_available)
        if output.get("error"):
            errors.append(str(output.get("error")))
        results = output.get("results")
        if not isinstance(results, list):
            continue
        output_source = _source_from_engine(str(output.get("engine") or ""))
        for rank, raw in enumerate(results, start=1):
            if not isinstance(raw, dict):
                continue
            key = _search_result_key(raw)
            merged = fused.setdefault(key, dict(raw))
            merged["_rrf_score"] = float(merged.get("_rrf_score", 0.0)) + 1.0 / (rrf_k + rank)
            merged.setdefault("query_ranks", [])
            if isinstance(merged["query_ranks"], list):
                merged["query_ranks"].append({"query_index": query_index, "rank": rank})
            merged["matched_by"] = _ordered_unique([
                "multi_query",
                *merged.get("matched_by", []),
                *(raw.get("matched_by") or [output_source]),
            ])
            merged["matched_fields"] = sorted(set(merged.get("matched_fields", [])) | set(raw.get("matched_fields", [])))
            merged["reasons"] = _ordered_unique([
                *merged.get("reasons", []),
                *raw.get("reasons", []),
                f"query {query_index} rank {rank}",
            ])

    results = list(fused.values())
    for item in results:
        item["score"] = round(float(item.pop("_rrf_score", 0.0)), 6)
        item["reason"] = "; ".join(str(reason) for reason in item.get("reasons", []) if str(reason).strip())
    results.sort(
        key=lambda item: (
            -float(item.get("score", 0.0)),
            str(item.get("table_name") or ""),
            str(item.get("type") or ""),
            str(item.get("column_name") or ""),
            str(item.get("name") or ""),
        )
    )

    vector_available_result = None
    if vector_values:
        vector_available_result = all(vector_values)
    multi_fuse_ms = (time.perf_counter() - merge_started) * 1000
    merge_ms = child_merge_ms + multi_fuse_ms
    response: dict[str, Any] = {
        "engine": "multi_query_fused",
        "original_query": original_query,
        "search_expressions": keyword_expression_list,
        "all_search_queries": expressions,
        "keyword_expressions": keyword_expression_list,
        "vector_expressions": vector_expression_list,
        "query_policy": query_policy,
        "planner_expression_count": len(keyword_expression_list) if query_policy != "single_question" else 0,
        "vector_expression_count": len(vector_expression_list),
        "question_embedding_call_count": question_embedding_call_count,
        "expression_embedding_call_count": expression_embedding_call_count,
        "embedding_call_count": question_embedding_call_count + expression_embedding_call_count,
        "db_search_call_count": len(search_outputs),
        "limit": limit,
        "results": results[:limit],
        "total_matches": len(results[:limit]),
        "retrieval_latency_ms": round(retrieval_latency_ms, 3),
        "embedding_build_time_ms": round(embedding_build_time_ms, 3),
        "keyword_recall_ms": round(keyword_recall_ms, 3),
        "query_embedding_ms": round(query_embedding_ms, 3),
        "question_embedding_ms": round(question_embedding_ms, 3),
        "expression_embedding_ms": round(expression_embedding_ms, 3),
        "vector_recall_ms": round(vector_recall_ms, 3),
        "merge_ms": round(merge_ms, 3),
        "multi_fuse_ms": round(multi_fuse_ms, 3),
        "rerank_ms": 0.0,
        "retrieval_only_ms": round(retrieval_only_ms, 3),
        "vector_available": vector_available_result,
    }
    if errors and len(errors) == len(search_outputs):
        response["error"] = errors[0]
    return response


def _prewarm_schema_embeddings_if_needed(db_session: Session, datasource_id: str) -> dict[str, Any] | None:
    mode = os.getenv("DBFOX_SCHEMA_RETRIEVAL_MODE", "keyword").strip().lower()
    if mode not in {"vector", "hybrid"}:
        return None

    started = time.perf_counter()
    try:
        build = ensure_schema_embeddings(db_session, datasource_id)
    except Exception:
        return {
            "step": {
                "tool_name": "schema.embedding.prewarm",
                "output": {
                    "retrieval_latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "embedding_build_time_ms": 0.0,
                    "vector_available": False,
                    "error": "Vector retrieval unavailable. Check embedding configuration and provider connectivity.",
                },
            }
        }

    return {
        "step": {
            "tool_name": "schema.embedding.prewarm",
            "output": {
                "retrieval_latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "embedding_build_time_ms": build.embedding_build_time_ms,
                "vector_available": True,
                "embedding_built_count": build.built_count,
                "embedding_model": build.model,
                "embedding_dimension": build.dimension,
            },
        }
    }


def _event_tuple(event: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    return (event,) if isinstance(event, dict) else ()


def _float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _search_result_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("type") or ""),
        str(item.get("table_name") or ""),
        str(item.get("column_name") or ""),
        str(item.get("name") or ""),
    )


def _source_from_engine(engine: str) -> str:
    lowered = engine.lower()
    if "hybrid" in lowered:
        return "hybrid"
    if "vector" in lowered:
        return "vector"
    return "keyword"


def _ordered_unique(values: Sequence[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _configure_eval_runtime_env() -> None:
    os.environ.setdefault("DBFOX_DISABLE_QUERY_HISTORY", "1")


def _create_temp_metadata_session(db_path: Path) -> Session:
    import engine.models as _models  # noqa: F401  # ensure models are registered
    from sqlalchemy import text as sa_text
    from engine.models import FTS5_DDL

    timeout_seconds = _sqlite_timeout_seconds()
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": timeout_seconds},
    )

    @sa_event.listens_for(engine, "connect")
    def _apply_eval_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={int(timeout_seconds * 1000)}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(sa_text("PRAGMA journal_mode=WAL"))
        conn.execute(sa_text(f"PRAGMA busy_timeout={int(timeout_seconds * 1000)}"))
        conn.execute(sa_text("PRAGMA synchronous=NORMAL"))
        conn.execute(sa_text(FTS5_DDL))
        conn.commit()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _sqlite_timeout_seconds() -> float:
    try:
        return float(os.getenv("DBFOX_SQLITE_TIMEOUT_SECONDS", "30"))
    except ValueError:
        return 30.0


def _close_metadata_session(db_session: Session) -> None:
    bind = None
    try:
        get_bind = getattr(db_session, "get_bind", None)
        if callable(get_bind):
            bind = get_bind()
    finally:
        db_session.close()
    dispose = getattr(bind, "dispose", None)
    if callable(dispose):
        dispose()


if __name__ == "__main__":
    raise SystemExit(main())
