from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from engine.evaluation.retrieval_ab.cli import (  # noqa: E402
    _close_metadata_session,
    _create_temp_metadata_session,
    _event_tuple,
    _prewarm_schema_embeddings_if_needed,
    _run_ai_assisted_retrieval_case,
)
from engine.evaluation.retrieval_ab.metrics import summarize_variant  # noqa: E402
from engine.evaluation.retrieval_ab.query_planner import plan_search_expressions  # noqa: E402
from engine.evaluation.retrieval_ab.report import write_reports  # noqa: E402
from engine.evaluation.retrieval_ab.runner import evaluate_artifacts  # noqa: E402
from engine.evaluation.retrieval_ab.spider_fixture import load_spider_cases  # noqa: E402
from engine.evaluation.spider.spider_eval import _ensure_spider_sqlite_datasource  # noqa: E402
from engine.evaluation.spider.spider_loader import load_spider_examples  # noqa: E402
from engine.models import SchemaColumn, SchemaSearchDoc, SchemaSearchEmbedding, SchemaTable  # noqa: E402
from engine.tools.db.embedding import ensure_schema_embeddings, resolve_embedding_config  # noqa: E402
from engine.tools.db.search import db_search  # noqa: E402


REPORT_DIR = Path(
    os.getenv(
        "DBFOX_EVAL_REPORT_DIR",
        str(PROJECT_ROOT / "reports" / "retrieval_ab_ai_assisted_real_provider"),
    )
)
CASES_PATH = Path(
    os.getenv(
        "DBFOX_EVAL_CASES",
        str(PROJECT_ROOT / "engine" / "tests" / "fixtures" / "spider_tiny" / "dev.json"),
    )
)
VARIANTS = ("keyword", "vector", "hybrid")
CASE_LIMIT = int(os.getenv("DBFOX_EVAL_CASE_LIMIT", os.getenv("DBFOX_EVAL_LIMIT", "5")))
RETRIEVAL_LIMIT = int(os.getenv("DBFOX_RETRIEVAL_TOP_K", "20"))
PLANNER_MODEL = "qwen-plus"


def main() -> int:
    _require_credentials()
    _clean_report_dir()
    os.environ["DBFOX_RETRIEVAL_TOP_K"] = str(RETRIEVAL_LIMIT)
    os.environ["DBFOX_RETRIEVAL_KEYWORD_TOP_K"] = "20"
    os.environ["DBFOX_RETRIEVAL_VECTOR_TOP_K"] = "20"
    os.environ.setdefault("DBFOX_DISABLE_QUERY_HISTORY", "1")

    cases = load_spider_cases(CASES_PATH, limit=CASE_LIMIT)
    examples = tuple(load_spider_examples(CASES_PATH.parent, split=CASES_PATH.stem, limit=CASE_LIMIT))
    if len(cases) != len(examples):
        raise RuntimeError(f"case/example count mismatch: {len(cases)} vs {len(examples)}")

    config = resolve_embedding_config()
    prep: dict[str, object] = {
        "cases_path": str(CASES_PATH),
        "case_count": len(cases),
        "variants": list(VARIANTS),
        "mode": "ai-assisted-retrieval",
        "planner_model": PLANNER_MODEL,
        "embedding_provider": "dashscope-openai-compatible",
        "embedding_base_url": config.base_url,
        "embedding_model": config.model,
        "embedding_dimension": config.dimension,
        "datasources": [],
        "sample_checks": [],
    }
    search_plans: list[dict[str, object]] = []
    db_session = _create_temp_metadata_session(REPORT_DIR / "metadata.sqlite")
    results = []
    try:
        datasource_by_db = {}
        for example in examples:
            if example.db_id in datasource_by_db:
                continue
            datasource_id, synced_tables = _ensure_spider_sqlite_datasource(db_session, example)
            datasource_by_db[example.db_id] = datasource_id
            cast_list(prep, "datasources").append(
                _prepare_datasource(db_session, datasource_id, example.db_id, synced_tables)
            )
            for mode in ("vector", "hybrid"):
                os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = mode
                sample = db_search(db_session, datasource_id, examples[0].question, RETRIEVAL_LIMIT)
                check = {
                    "db_id": example.db_id,
                    "mode": mode,
                    "engine": sample.get("engine"),
                    "vector_available": sample.get("vector_available"),
                    "total_matches": sample.get("total_matches"),
                    "retrieval_latency_ms": sample.get("retrieval_latency_ms"),
                    "embedding_build_time_ms": sample.get("embedding_build_time_ms"),
                    "error": sample.get("error"),
                }
                cast_list(prep, "sample_checks").append(check)
                if sample.get("vector_available") is not True:
                    raise RuntimeError(f"{mode} sample vector retrieval unavailable: {check}")

        plan_cache: dict[str, tuple[str, ...]] = {}
        for case in cases:
            expressions = plan_search_expressions(case, model=PLANNER_MODEL)
            plan_cache[case.case_id] = expressions
            search_plans.append(
                {
                    "case_id": case.case_id,
                    "db_id": case.db_id,
                    "question": case.question,
                    "search_expressions": list(expressions),
                }
            )

        for variant in VARIANTS:
            os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = variant
            for case, example in zip(cases, examples, strict=True):
                datasource_id = datasource_by_db[example.db_id]
                prewarm_event = _prewarm_schema_embeddings_if_needed(db_session, datasource_id)
                artifacts = _run_ai_assisted_retrieval_case(
                    db_session=db_session,
                    datasource_id=datasource_id,
                    case=case,
                    limit=RETRIEVAL_LIMIT,
                    model=PLANNER_MODEL,
                    search_expressions=plan_cache[case.case_id],
                    pre_events=_event_tuple(prewarm_event),
                )
                results.append(evaluate_artifacts(case, variant, artifacts, mode="ai-assisted-retrieval"))
    finally:
        _close_metadata_session(db_session)

    summaries = tuple(
        summarize_variant(variant, (row for row in results if row.variant == variant))
        for variant in VARIANTS
    )
    paths = write_reports(
        output_dir=REPORT_DIR,
        benchmark="spider",
        variants=VARIANTS,
        summaries=summaries,
        cases=tuple(results),
    )
    prep_path = REPORT_DIR / "prep_check.json"
    plans_path = REPORT_DIR / "search_plans.json"
    prep_path.write_text(json.dumps(prep, ensure_ascii=False, indent=2), encoding="utf-8")
    plans_path.write_text(json.dumps(search_plans, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"prep: {prep_path}")
    print(f"search_plans: {plans_path}")
    print(f"summary: {paths.summary_json}")
    print(f"cases: {paths.cases_csv}")
    print(f"report: {paths.markdown_report}")
    for row in summaries:
        print(
            json.dumps(
                {
                    "variant": row.variant,
                    "total_cases": row.total_cases,
                    "table_recall_at_5": row.table_recall_at_5,
                    "column_recall_at_10": row.column_recall_at_10,
                    "vector_available_rate": row.vector_available_rate,
                    "db_search_call_count": row.db_search_call_count,
                    "p95_retrieval_latency_ms": row.p95_retrieval_latency_ms,
                    "p95_embedding_build_time_ms": row.p95_embedding_build_time_ms,
                    "failure_class_counts": row.failure_class_counts,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return 0


def _prepare_datasource(db_session, datasource_id: str, db_id: str, synced_tables: list[str]) -> dict[str, object]:
    doc_count = (
        db_session.query(SchemaSearchDoc)
        .filter(SchemaSearchDoc.datasource_id == datasource_id)
        .count()
    )
    table_count = (
        db_session.query(SchemaTable)
        .filter(SchemaTable.data_source_id == datasource_id)
        .count()
    )
    column_count = (
        db_session.query(SchemaColumn)
        .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
        .filter(SchemaTable.data_source_id == datasource_id)
        .count()
    )
    build = ensure_schema_embeddings(db_session, datasource_id)
    config = resolve_embedding_config()
    embed_count = (
        db_session.query(SchemaSearchEmbedding)
        .filter(
            SchemaSearchEmbedding.datasource_id == datasource_id,
            SchemaSearchEmbedding.embedding_model == config.model,
            SchemaSearchEmbedding.embedding_dimension == config.dimension,
        )
        .count()
    )
    if doc_count <= 0:
        raise RuntimeError(f"{db_id} has no schema_search_docs")
    if doc_count != embed_count:
        raise RuntimeError(f"{db_id} embedding count mismatch: docs={doc_count}, embeddings={embed_count}")
    return {
        "db_id": db_id,
        "datasource_id": datasource_id,
        "synced_tables": synced_tables,
        "schema_table_count": table_count,
        "schema_column_count": column_count,
        "schema_search_doc_count": doc_count,
        "embedding_total_docs": build.total_docs,
        "embedding_built_count": build.built_count,
        "embedding_stale_count": build.stale_count,
        "embedding_row_count": embed_count,
        "embedding_build_time_ms": build.embedding_build_time_ms,
        "docs_equal_embeddings": doc_count == embed_count,
    }


def _require_credentials() -> None:
    if not any(os.getenv(name, "").strip() for name in ("OPENAI_API_KEY", "QWEN_API_KEY", "DBFOX_EMBEDDING_API_KEY", "DASHSCOPE_API_KEY")):
        raise RuntimeError("Planner/embedding API key is not configured.")


def _clean_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    resolved = REPORT_DIR.resolve()
    expected_parent = (PROJECT_ROOT / "reports").resolve()
    if expected_parent not in resolved.parents:
        raise RuntimeError(f"Refusing to clean unexpected report dir: {resolved}")
    for child in REPORT_DIR.iterdir():
        if child.name == Path(__file__).name:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def cast_list(mapping: dict[str, object], key: str) -> list[dict[str, object]]:
    value = mapping[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
