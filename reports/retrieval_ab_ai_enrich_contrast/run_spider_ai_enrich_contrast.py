from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from engine.ai_enrich import ai_enrich_catalog  # noqa: E402
from engine.environment.schema_catalog_sync import rebuild_search_docs  # noqa: E402
from engine.evaluation.retrieval_ab.cli import (  # noqa: E402
    _close_metadata_session,
    _create_temp_metadata_session,
    _run_ai_assisted_retrieval_case,
)
from engine.evaluation.retrieval_ab.contrast import summarize_contrast_rows  # noqa: E402
from engine.evaluation.retrieval_ab.query_planner import plan_search_expressions  # noqa: E402
from engine.evaluation.retrieval_ab.runner import evaluate_artifacts  # noqa: E402
from engine.evaluation.retrieval_ab.spider_fixture import EvaluationCase, spider_example_to_case  # noqa: E402
from engine.evaluation.spider.spider_loader import SpiderExample, load_spider_examples  # noqa: E402
from engine.models import DataSource, SchemaColumn, SchemaSearchDoc, SchemaSearchEmbedding, SchemaTable  # noqa: E402
from engine.tools.db.embedding import ensure_schema_embeddings, resolve_embedding_config  # noqa: E402


def _split_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


REPORT_DIR = Path(
    os.getenv(
        "DBFOX_EVAL_REPORT_DIR",
        str(PROJECT_ROOT / "reports" / "retrieval_ab_ai_enrich_contrast"),
    )
)
CASES_PATH = Path(
    os.getenv(
        "DBFOX_EVAL_CASES",
        str(PROJECT_ROOT / "engine" / "tests" / "fixtures" / "spider_tiny" / "dev.json"),
    )
)
CASE_LIMIT = int(os.getenv("DBFOX_EVAL_CASE_LIMIT", os.getenv("DBFOX_EVAL_LIMIT", "10")))
SAMPLE_STRATEGY = os.getenv("DBFOX_EVAL_SAMPLE_STRATEGY", "head").strip() or "head"
SAMPLE_DB_LIMIT = int(os.getenv("DBFOX_EVAL_DB_LIMIT", "0"))
RETRIEVAL_LIMIT = int(os.getenv("DBFOX_RETRIEVAL_TOP_K", "20"))
PLANNER_MODEL = os.getenv("DBFOX_RETRIEVAL_PLANNER_MODEL", "qwen-plus")
ENRICH_MODEL = os.getenv("DBFOX_AI_ENRICH_MODEL", PLANNER_MODEL)
EVAL_VARIANT_NAMES = _split_env(
    "DBFOX_RETRIEVAL_EVAL_VARIANTS",
    (
        "keyword_raw,vector_raw,keyword_enriched,vector_enriched,"
        "hybrid_raw_question,hybrid_keyword_enriched_vector_raw_question,"
        "hybrid_keyword_raw_vector_enriched_question,hybrid_enriched_question"
    ),
)
RETRIEVERS = _split_env("DBFOX_RETRIEVAL_VARIANTS", "keyword,vector,hybrid")
QUERY_MODES = _split_env("DBFOX_QUERY_MODES", "single,multi")


@dataclass(frozen=True)
class EvalVariant:
    name: str
    retriever: str
    keyword_profile: str
    vector_profile: str
    query_policy: str
    diagnostic: bool = False

    @property
    def keyword_corpus_profile(self) -> str:
        return self.keyword_profile if self.retriever in {"keyword", "hybrid"} else "none"

    @property
    def vector_corpus_profile(self) -> str:
        return self.vector_profile if self.retriever in {"vector", "hybrid"} else "none"

    @property
    def needs_enriched_catalog(self) -> bool:
        return "enriched" in {self.keyword_profile, self.vector_profile}

    @property
    def corpus_profile(self) -> str:
        if self.retriever == "keyword":
            return self.keyword_profile
        if self.retriever == "vector":
            return self.vector_profile
        return self.keyword_profile


DEFAULT_EVAL_VARIANTS: dict[str, EvalVariant] = {
    "keyword_raw": EvalVariant("keyword_raw", "keyword", "raw", "none", "multi_keyword_vector_question"),
    "vector_raw": EvalVariant("vector_raw", "vector", "none", "raw", "single_question"),
    "keyword_enriched": EvalVariant("keyword_enriched", "keyword", "enriched", "none", "multi_keyword_vector_question"),
    "vector_enriched": EvalVariant("vector_enriched", "vector", "none", "enriched", "single_question"),
    "hybrid_raw_question": EvalVariant("hybrid_raw_question", "hybrid", "raw", "raw", "multi_keyword_vector_question"),
    "hybrid_keyword_enriched_vector_raw_question": EvalVariant(
        "hybrid_keyword_enriched_vector_raw_question",
        "hybrid",
        "enriched",
        "raw",
        "multi_keyword_vector_question",
    ),
    "hybrid_keyword_raw_vector_enriched_question": EvalVariant(
        "hybrid_keyword_raw_vector_enriched_question",
        "hybrid",
        "raw",
        "enriched",
        "multi_keyword_vector_question",
    ),
    "hybrid_enriched_question": EvalVariant(
        "hybrid_enriched_question",
        "hybrid",
        "enriched",
        "enriched",
        "multi_keyword_vector_question",
    ),
    "hybrid_keyword_enriched_vector_raw_expression_each": EvalVariant(
        "hybrid_keyword_enriched_vector_raw_expression_each",
        "hybrid",
        "enriched",
        "raw",
        "multi_keyword_vector_expression_each",
        True,
    ),
    "hybrid_enriched_expression_each": EvalVariant(
        "hybrid_enriched_expression_each",
        "hybrid",
        "enriched",
        "enriched",
        "multi_keyword_vector_expression_each",
        True,
    ),
}
DEFAULT_EVAL_VARIANTS.update(
    {
        "hybrid_raw": DEFAULT_EVAL_VARIANTS["hybrid_raw_question"],
        "hybrid_keyword_enriched_vector_raw": DEFAULT_EVAL_VARIANTS["hybrid_keyword_enriched_vector_raw_question"],
        "hybrid_keyword_raw_vector_enriched": DEFAULT_EVAL_VARIANTS["hybrid_keyword_raw_vector_enriched_question"],
        "hybrid_enriched": DEFAULT_EVAL_VARIANTS["hybrid_enriched_question"],
    }
)
DEFAULT_EVAL_VARIANT_NAMES = (
    "keyword_raw",
    "vector_raw",
    "keyword_enriched",
    "vector_enriched",
    "hybrid_raw_question",
    "hybrid_keyword_enriched_vector_raw_question",
    "hybrid_keyword_raw_vector_enriched_question",
    "hybrid_enriched_question",
)
LEGACY_SCHEMA_VARIANTS = {"base", "ai_enriched", "full_enrich", "keyword_only_enrich", "vector_only_enrich"}


class ProgressWriter:
    def __init__(self, path: Path, *, stdout: bool = True) -> None:
        self.path = path
        self.stdout = stdout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def emit(self, event: str, **payload: Any) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        line = json.dumps(row, ensure_ascii=False, sort_keys=True)
        self._fh.write(line + "\n")
        self._fh.flush()
        if self.stdout:
            print(line, flush=True)

    def close(self) -> None:
        self._fh.close()


def resolve_eval_variants(names: tuple[str, ...]) -> tuple[EvalVariant, ...]:
    requested = names or DEFAULT_EVAL_VARIANT_NAMES
    unknown = [name for name in requested if name not in DEFAULT_EVAL_VARIANTS]
    if unknown:
        if any(name in LEGACY_SCHEMA_VARIANTS for name in unknown):
            raise RuntimeError(
                "Use explicit retrieval eval variants such as keyword_raw, vector_raw, "
                "keyword_enriched, vector_enriched, hybrid_raw_question, "
                "hybrid_keyword_enriched_vector_raw_question, "
                "hybrid_keyword_raw_vector_enriched_question, hybrid_enriched_question."
            )
        raise RuntimeError(f"Unsupported DBFOX_RETRIEVAL_EVAL_VARIANTS: {', '.join(unknown)}")
    return tuple(DEFAULT_EVAL_VARIANTS[name] for name in requested)


def _variant_dict(variant: EvalVariant) -> dict[str, str]:
    return {
        "name": variant.name,
        "retriever": variant.retriever,
        "keyword_profile": variant.keyword_profile,
        "vector_profile": variant.vector_profile,
        "keyword_corpus_profile": variant.keyword_corpus_profile,
        "vector_corpus_profile": variant.vector_corpus_profile,
        "query_policy": variant.query_policy,
        "diagnostic": str(variant.diagnostic).lower(),
        "active_doc_profile": _active_doc_profile(variant),
    }


def _active_doc_profile(variant: EvalVariant) -> str:
    return variant.corpus_profile


def _variants_by_doc_profile(variants: tuple[EvalVariant, ...]) -> list[tuple[str, list[EvalVariant]]]:
    grouped: dict[str, list[EvalVariant]] = {"raw": [], "enriched": []}
    for variant in variants:
        grouped.setdefault(_active_doc_profile(variant), []).append(variant)
    return [(profile, items) for profile, items in grouped.items() if items]


def datasource_for_variant(
    corpus_by_db: dict[str, dict[str, str]],
    db_id: str,
    variant: EvalVariant,
) -> str:
    try:
        return corpus_by_db[db_id][variant.corpus_profile]
    except KeyError as exc:
        raise RuntimeError(f"Prepared corpus datasource missing for db={db_id}, profile={variant.corpus_profile}") from exc


def vector_datasource_for_variant(
    corpus_by_db: dict[str, dict[str, str]],
    db_id: str,
    variant: EvalVariant,
) -> str:
    profile = variant.vector_corpus_profile
    if profile == "none":
        return datasource_for_variant(corpus_by_db, db_id, variant)
    try:
        return corpus_by_db[db_id][profile]
    except KeyError as exc:
        raise RuntimeError(f"Prepared vector corpus datasource missing for db={db_id}, profile={profile}") from exc


def query_policy_for_variant(variant: EvalVariant, query_mode: str) -> str:
    if query_mode == "single":
        return "single_question"
    return variant.query_policy


def run_planner_warmup(warmup: Callable[[], Any], progress: ProgressWriter) -> dict[str, Any]:
    started = time.perf_counter()
    warmup()
    result = {
        "planner_warmup_ms": round((time.perf_counter() - started) * 1000, 3),
        "planner_warmup_in_case_latency": False,
    }
    progress.emit("planner_warmup_done", **result)
    return result


def _warmup_planner_client() -> None:
    from engine.evaluation.retrieval_ab.query_planner import _planner_api_base, _planner_api_key
    from engine.llm.factory import get_chat_model

    get_chat_model(
        model_name=PLANNER_MODEL,
        api_key=_planner_api_key(),
        api_base=_planner_api_base(),
        temperature=0.0,
        max_tokens=1,
        timeout=60.0,
    )


def main() -> int:
    _require_credentials()
    _clean_report_dir()
    eval_variants = resolve_eval_variants(EVAL_VARIANT_NAMES)
    progress = ProgressWriter(
        Path(os.getenv("DBFOX_EVAL_PROGRESS_PATH", str(REPORT_DIR / "progress_events.jsonl"))),
        stdout=os.getenv("DBFOX_EVAL_PROGRESS_STDOUT", "1").strip() != "0",
    )
    os.environ["DBFOX_RETRIEVAL_TOP_K"] = str(RETRIEVAL_LIMIT)
    os.environ.setdefault("DBFOX_RETRIEVAL_KEYWORD_TOP_K", str(RETRIEVAL_LIMIT))
    os.environ.setdefault("DBFOX_RETRIEVAL_VECTOR_TOP_K", str(RETRIEVAL_LIMIT))
    os.environ.setdefault("DBFOX_DISABLE_QUERY_HISTORY", "1")

    cases, examples = _load_case_example_pairs(
        CASES_PATH,
        limit=CASE_LIMIT,
        sample_strategy=SAMPLE_STRATEGY,
        db_limit=SAMPLE_DB_LIMIT,
    )
    progress.emit(
        "run_start",
        cases_path=str(CASES_PATH),
        case_count=len(cases),
        eval_variants=[variant.name for variant in eval_variants],
        retrievers=sorted({variant.retriever for variant in eval_variants}),
        query_modes=list(QUERY_MODES),
    )

    config = resolve_embedding_config()
    prep: dict[str, Any] = {
        "cases_path": str(CASES_PATH),
        "case_count": len(cases),
        "sample_strategy": SAMPLE_STRATEGY,
        "sample_db_limit": SAMPLE_DB_LIMIT,
        "selected_db_counts": _db_counts(examples),
        "eval_variants": [_variant_dict(variant) for variant in eval_variants],
        "retrievers": sorted({variant.retriever for variant in eval_variants}),
        "query_modes": list(QUERY_MODES),
        "planner_model": PLANNER_MODEL,
        "planner_warmup": None,
        "ai_enrich_model": ENRICH_MODEL,
        "embedding_base_url": config.base_url,
        "embedding_model": config.model,
        "embedding_dimension": config.dimension,
        "datasources": [],
        "corpus_stats": [],
        "ai_enrich_results": [],
    }
    case_rows: list[dict[str, Any]] = []
    search_plans: list[dict[str, Any]] = []

    previous_retrieval_mode = os.environ.get("DBFOX_SCHEMA_RETRIEVAL_MODE")
    previous_vector_datasource_id = os.environ.get("DBFOX_SCHEMA_VECTOR_DATASOURCE_ID")
    db_session = _create_temp_metadata_session(REPORT_DIR / "metadata.sqlite")
    try:
        corpus_by_db: dict[str, dict[str, str]] = {}
        datasource_stats_seen: set[str] = set()
        for example in examples:
            if example.db_id in corpus_by_db:
                continue
            corpus_by_db[example.db_id] = {}
            for profile in ("raw", "enriched"):
                progress.emit("datasource_sync_start", db_id=example.db_id, corpus_profile=profile)
                datasource_id, synced_tables = _ensure_profiled_spider_datasource(db_session, example, profile)
                corpus_by_db[example.db_id][profile] = datasource_id
                if datasource_id not in datasource_stats_seen:
                    prep["datasources"].append(
                        _datasource_stats(db_session, datasource_id, example.db_id, synced_tables, corpus_profile=profile)
                    )
                    datasource_stats_seen.add(datasource_id)
                progress.emit(
                    "datasource_sync_done",
                    db_id=example.db_id,
                    corpus_profile=profile,
                    datasource_id=datasource_id,
                    table_count=len(synced_tables),
                )

        plan_cache: dict[str, tuple[tuple[str, ...], float]] = {}
        if "multi" in QUERY_MODES:
            prep["planner_warmup"] = run_planner_warmup(_warmup_planner_client, progress)
            for case in cases:
                progress.emit("plan_start", case_id=case.case_id, db_id=case.db_id)
                started = time.perf_counter()
                expressions = plan_search_expressions(case, model=PLANNER_MODEL)
                planner_latency_ms = round((time.perf_counter() - started) * 1000, 3)
                plan_cache[case.case_id] = (expressions, planner_latency_ms)
                search_plans.append(
                    {
                        "case_id": case.case_id,
                        "db_id": case.db_id,
                        "question": case.question,
                        "planner_latency_ms": planner_latency_ms,
                        "search_expressions": list(expressions),
                    }
                )
                progress.emit(
                    "plan_done",
                    case_id=case.case_id,
                    db_id=case.db_id,
                    planner_latency_ms=planner_latency_ms,
                    expression_count=len(expressions),
                )

        prep["ai_enrich_results"].extend(_run_ai_enrichment(db_session, _datasources_for_profile(corpus_by_db, "enriched"), progress))

        for doc_profile in ("raw", "enriched"):
            progress.emit(
                "schema_profile_start",
                doc_profile=doc_profile,
                eval_variants=[variant.name for variant in eval_variants if doc_profile in {variant.keyword_corpus_profile, variant.vector_corpus_profile}],
            )
            include_ai_metadata = doc_profile == "enriched"
            for datasource_id in _datasources_for_profile(corpus_by_db, doc_profile).values():
                progress.emit("corpus_rebuild_start", schema_variant=doc_profile, datasource_id=datasource_id)
                rebuild_search_docs(db_session, datasource_id, include_ai_metadata=include_ai_metadata)
                progress.emit("corpus_rebuild_done", schema_variant=doc_profile, datasource_id=datasource_id)
            db_session.commit()

            corpus_stats = _prepare_corpus_variant(
                db_session,
                _datasources_for_profile(corpus_by_db, doc_profile),
                doc_profile,
                progress,
                needs_vectors=True,
            )
            prep["corpus_stats"].extend(corpus_stats)
            if doc_profile == "enriched" and not any(row["ai_metadata_doc_count"] > 0 for row in corpus_stats):
                raise RuntimeError("AI-enriched corpus has no AI metadata in schema_search_docs.")
            progress.emit("schema_profile_done", doc_profile=doc_profile)

        for variant in eval_variants:
            os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = variant.retriever
            doc_profile = _active_doc_profile(variant)
            for query_mode in QUERY_MODES:
                query_policy = query_policy_for_variant(variant, query_mode)
                progress.emit(
                    "matrix_cell_start",
                    schema_variant=variant.name,
                    retriever=variant.retriever,
                    query_mode=query_mode,
                    query_policy=query_policy,
                    keyword_profile=variant.keyword_profile,
                    vector_profile=variant.vector_profile,
                    keyword_corpus_profile=variant.keyword_corpus_profile,
                    vector_corpus_profile=variant.vector_corpus_profile,
                    diagnostic=variant.diagnostic,
                    doc_profile=doc_profile,
                    case_count=len(cases),
                )
                for case, example in zip(cases, examples, strict=True):
                    datasource_id = datasource_for_variant(corpus_by_db, example.db_id, variant)
                    vector_datasource_id = vector_datasource_for_variant(corpus_by_db, example.db_id, variant)
                    if variant.retriever == "hybrid":
                        os.environ["DBFOX_SCHEMA_VECTOR_DATASOURCE_ID"] = vector_datasource_id
                    else:
                        os.environ.pop("DBFOX_SCHEMA_VECTOR_DATASOURCE_ID", None)
                    expressions, planner_latency_ms = _expressions_for_case(case, query_mode, query_policy, plan_cache)
                    progress.emit(
                        "case_start",
                        schema_variant=variant.name,
                        retriever=variant.retriever,
                        query_mode=query_mode,
                        query_policy=query_policy,
                        case_id=case.case_id,
                        db_id=case.db_id,
                        datasource_id=datasource_id,
                        vector_datasource_id=vector_datasource_id if variant.retriever == "hybrid" else None,
                        expression_count=len(expressions),
                    )
                    artifacts = _run_ai_assisted_retrieval_case(
                        db_session=db_session,
                        datasource_id=datasource_id,
                        vector_datasource_id=vector_datasource_id,
                        case=case,
                        limit=RETRIEVAL_LIMIT,
                        model=PLANNER_MODEL,
                        search_expressions=expressions,
                        query_policy=query_policy,
                    )
                    evaluated = evaluate_artifacts(case, variant.retriever, artifacts, mode="ai-assisted-retrieval")
                    fused = _fused_output(artifacts.events)
                    case_rows.append(
                        _case_row(
                            schema_variant=variant.name,
                            retriever=variant.retriever,
                            query_mode=query_mode,
                            query_policy=query_policy,
                            keyword_profile=variant.keyword_profile,
                            vector_profile=variant.vector_profile,
                            keyword_corpus_profile=variant.keyword_corpus_profile,
                            vector_corpus_profile=variant.vector_corpus_profile,
                            doc_profile=doc_profile,
                            diagnostic=variant.diagnostic,
                            evaluated=evaluated,
                            fused=fused,
                            planner_latency_ms=planner_latency_ms,
                        )
                    )
                    progress.emit(
                        "case_done",
                        schema_variant=variant.name,
                        retriever=variant.retriever,
                        query_mode=query_mode,
                        query_policy=query_policy,
                        case_id=case.case_id,
                        db_id=case.db_id,
                        table_recall_at_5=evaluated.table_recall_at_5,
                        column_recall_at_10=evaluated.column_recall_at_10,
                        query_embedding_ms=_float_value(fused.get("query_embedding_ms")),
                        keyword_recall_ms=_float_value(fused.get("keyword_recall_ms")),
                        vector_recall_ms=_float_value(fused.get("vector_recall_ms")),
                        merge_ms=_float_value(fused.get("merge_ms")),
                        retrieval_only_ms=_float_value(fused.get("retrieval_only_ms") or fused.get("retrieval_latency_ms")),
                        e2e_ms=round(planner_latency_ms + _float_value(fused.get("retrieval_only_ms") or fused.get("retrieval_latency_ms")), 3),
                        failure_class=evaluated.failure_class,
                    )
                progress.emit(
                    "matrix_cell_done",
                    schema_variant=variant.name,
                    retriever=variant.retriever,
                    query_mode=query_mode,
                    query_policy=query_policy,
                )
    finally:
        if previous_retrieval_mode is None:
            os.environ.pop("DBFOX_SCHEMA_RETRIEVAL_MODE", None)
        else:
            os.environ["DBFOX_SCHEMA_RETRIEVAL_MODE"] = previous_retrieval_mode
        if previous_vector_datasource_id is None:
            os.environ.pop("DBFOX_SCHEMA_VECTOR_DATASOURCE_ID", None)
        else:
            os.environ["DBFOX_SCHEMA_VECTOR_DATASOURCE_ID"] = previous_vector_datasource_id
        _close_metadata_session(db_session)

    summaries = summarize_contrast_rows(case_rows)
    _write_outputs(prep, search_plans, case_rows, summaries)
    progress.emit("run_done", summary_path=str(REPORT_DIR / "contrast_summary.json"), case_rows=len(case_rows))
    progress.close()
    print(f"prep: {REPORT_DIR / 'prep_check.json'}")
    print(f"search_plans: {REPORT_DIR / 'search_plans.json'}")
    print(f"summary: {REPORT_DIR / 'contrast_summary.json'}")
    print(f"cases: {REPORT_DIR / 'contrast_cases.csv'}")
    print(f"report: {REPORT_DIR / 'contrast_report.md'}")
    for row in summaries:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


def _require_credentials() -> None:
    if not any(os.getenv(name, "").strip() for name in ("OPENAI_API_KEY", "QWEN_API_KEY", "DBFOX_EMBEDDING_API_KEY", "DASHSCOPE_API_KEY")):
        raise RuntimeError("Planner/enrichment/embedding API key is not configured.")


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


def _datasources_for_profile(corpus_by_db: dict[str, dict[str, str]], profile: str) -> dict[str, str]:
    return {db_id: profiles[profile] for db_id, profiles in corpus_by_db.items() if profile in profiles}


def _ensure_profiled_spider_datasource(
    db_session,
    example: SpiderExample,
    corpus_profile: str,
) -> tuple[str, list[str]]:
    import uuid
    from engine.environment.schema_catalog_sync import ensure_catalog

    db_path = str(example.db_path.resolve())
    host = f"spider-eval-{corpus_profile}"
    existing = (
        db_session.query(DataSource)
        .filter(DataSource.host == host, DataSource.database_name == db_path)
        .first()
    )
    if existing is not None:
        if existing.last_sync_status != "success":
            ensure_catalog(db_session, str(existing.id))
        return str(existing.id), _get_synced_table_names(db_session, str(existing.id))

    ds_id = f"spider_{example.db_id}_{corpus_profile}_{uuid.uuid4().hex[:8]}"
    datasource = DataSource(
        id=ds_id,
        name=f"Spider {example.db_id} {corpus_profile}",
        db_type="sqlite",
        host=host,
        port=0,
        database_name=db_path,
        username="",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()
    ensure_catalog(db_session, ds_id)
    return ds_id, _get_synced_table_names(db_session, ds_id)


def _get_synced_table_names(db_session, datasource_id: str) -> list[str]:
    rows = (
        db_session.query(SchemaTable.table_name)
        .filter(SchemaTable.data_source_id == datasource_id)
        .all()
    )
    return sorted([row[0] for row in rows])


def _datasource_stats(
    db_session,
    datasource_id: str,
    db_id: str,
    synced_tables: list[str],
    *,
    corpus_profile: str,
) -> dict[str, Any]:
    return {
        "db_id": db_id,
        "corpus_profile": corpus_profile,
        "datasource_id": datasource_id,
        "synced_tables": synced_tables,
        "schema_table_count": db_session.query(SchemaTable).filter(SchemaTable.data_source_id == datasource_id).count(),
        "schema_column_count": (
            db_session.query(SchemaColumn)
            .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
            .filter(SchemaTable.data_source_id == datasource_id)
            .count()
        ),
    }


def _load_case_example_pairs(
    cases_path: Path,
    *,
    limit: int,
    sample_strategy: str,
    db_limit: int = 0,
) -> tuple[tuple[EvaluationCase, ...], tuple[SpiderExample, ...]]:
    examples = tuple(load_spider_examples(cases_path.parent, split=cases_path.stem))
    selected = _select_examples(examples, limit=limit, sample_strategy=sample_strategy, db_limit=db_limit)
    cases = tuple(spider_example_to_case(example, index=index) for index, example in enumerate(selected, start=1))
    return cases, selected


def _select_examples(
    examples: tuple[SpiderExample, ...],
    *,
    limit: int,
    sample_strategy: str,
    db_limit: int = 0,
) -> tuple[SpiderExample, ...]:
    if limit <= 0:
        return ()
    if sample_strategy == "head":
        return examples[:limit]
    if sample_strategy != "round_robin_db":
        raise RuntimeError(f"Unsupported DBFOX_EVAL_SAMPLE_STRATEGY: {sample_strategy}")

    grouped: dict[str, list[SpiderExample]] = {}
    db_order: list[str] = []
    for example in examples:
        if example.db_id not in grouped:
            if db_limit > 0 and len(db_order) >= db_limit:
                continue
            grouped[example.db_id] = []
            db_order.append(example.db_id)
        grouped[example.db_id].append(example)

    selected: list[SpiderExample] = []
    index = 0
    while len(selected) < limit:
        made_progress = False
        for db_id in db_order:
            bucket = grouped[db_id]
            if index < len(bucket):
                selected.append(bucket[index])
                made_progress = True
                if len(selected) >= limit:
                    break
        if not made_progress:
            break
        index += 1
    return tuple(selected)


def _db_counts(examples: tuple[SpiderExample, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for example in examples:
        counts[example.db_id] = counts.get(example.db_id, 0) + 1
    return counts


def _run_ai_enrichment(db_session, datasource_by_db: dict[str, str], progress: ProgressWriter) -> list[dict[str, Any]]:
    results = []
    for db_id, datasource_id in datasource_by_db.items():
        progress.emit("ai_enrich_start", db_id=db_id, datasource_id=datasource_id)
        started = time.perf_counter()
        result = ai_enrich_catalog(
            db_session,
            datasource_id,
            api_key=_first_env("DBFOX_AI_ENRICH_API_KEY", "DBFOX_RETRIEVAL_PLANNER_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY", "DBFOX_EMBEDDING_API_KEY", "DASHSCOPE_API_KEY"),
            api_base=_first_env("DBFOX_AI_ENRICH_BASE_URL", "DBFOX_RETRIEVAL_PLANNER_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE", "DBFOX_EMBEDDING_BASE_URL"),
            model_name=ENRICH_MODEL,
        )
        result = dict(result)
        result.update(
            {
                "db_id": db_id,
                "datasource_id": datasource_id,
                "ai_enrich_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
        if result.get("ai_enriched") is not True:
            raise RuntimeError(f"AI enrichment failed for {db_id}: {result}")
        results.append(result)
        progress.emit(
            "ai_enrich_done",
            db_id=db_id,
            datasource_id=datasource_id,
            ai_enrich_latency_ms=result["ai_enrich_latency_ms"],
            enriched_count=result.get("enriched_count"),
        )
    return results


def _prepare_corpus_variant(
    db_session,
    datasource_by_db: dict[str, str],
    doc_profile: str,
    progress: ProgressWriter,
    *,
    needs_vectors: bool,
) -> list[dict[str, Any]]:
    rows = []
    config = resolve_embedding_config()
    for db_id, datasource_id in datasource_by_db.items():
        progress.emit("corpus_prepare_start", schema_variant=doc_profile, doc_profile=doc_profile, db_id=db_id, datasource_id=datasource_id)
        build = ensure_schema_embeddings(db_session, datasource_id) if needs_vectors else None
        doc_count = db_session.query(SchemaSearchDoc).filter(SchemaSearchDoc.datasource_id == datasource_id).count()
        ai_doc_count = (
            db_session.query(SchemaSearchDoc)
            .filter(
                SchemaSearchDoc.datasource_id == datasource_id,
                (
                    (SchemaSearchDoc.ai_description.isnot(None))
                    | (SchemaSearchDoc.semantic_tags.isnot(None))
                    | (SchemaSearchDoc.business_terms.isnot(None))
                    | (SchemaSearchDoc.aliases.isnot(None))
                ),
            )
            .count()
        )
        embed_count = (
            db_session.query(SchemaSearchEmbedding)
            .filter(
                SchemaSearchEmbedding.datasource_id == datasource_id,
                SchemaSearchEmbedding.embedding_model == config.model,
                SchemaSearchEmbedding.embedding_dimension == config.dimension,
            )
            .count()
        )
        rows.append(
            {
                "schema_variant": doc_profile,
                "doc_profile": doc_profile,
                "db_id": db_id,
                "datasource_id": datasource_id,
                "schema_search_doc_count": doc_count,
                "ai_metadata_doc_count": ai_doc_count,
                "embedding_row_count": embed_count,
                "embedding_built_count": build.built_count if build else 0,
                "embedding_stale_count": build.stale_count if build else 0,
                "embedding_build_time_ms": build.embedding_build_time_ms if build else 0.0,
                "docs_equal_embeddings": doc_count == embed_count if needs_vectors else None,
            }
        )
        progress.emit(
            "corpus_prepare_done",
            schema_variant=doc_profile,
            doc_profile=doc_profile,
            db_id=db_id,
            datasource_id=datasource_id,
            schema_search_doc_count=doc_count,
            ai_metadata_doc_count=ai_doc_count,
            embedding_row_count=embed_count,
            embedding_built_count=build.built_count if build else 0,
        )
    return rows


def _expressions_for_case(
    case,
    query_mode: str,
    query_policy: str,
    plan_cache: dict[str, tuple[tuple[str, ...], float]],
) -> tuple[tuple[str, ...], float]:
    if query_mode == "single" or query_policy == "single_question":
        return (case.question,), 0.0
    expressions, planner_latency_ms = plan_cache[case.case_id]
    return expressions, planner_latency_ms


def _fused_output(events: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    for event in reversed(events):
        step = event.get("step")
        if isinstance(step, dict) and step.get("tool_name") == "db.search.fused":
            output = step.get("output")
            if isinstance(output, dict):
                return output
    return {}


def _case_row(
    *,
    schema_variant: str,
    retriever: str,
    query_mode: str,
    query_policy: str,
    keyword_profile: str,
    vector_profile: str,
    keyword_corpus_profile: str,
    vector_corpus_profile: str,
    doc_profile: str,
    diagnostic: bool,
    evaluated,
    fused: dict[str, Any],
    planner_latency_ms: float,
) -> dict[str, Any]:
    query_embedding_ms = _float_value(fused.get("query_embedding_ms"))
    retrieval_only_ms = _float_value(fused.get("retrieval_only_ms") or fused.get("retrieval_latency_ms"))
    modeled_online_ms = round(planner_latency_ms + retrieval_only_ms, 3)
    measured_provider_ms = round(planner_latency_ms + query_embedding_ms, 3)
    return {
        "schema_variant": schema_variant,
        "retriever": retriever,
        "query_mode": query_mode,
        "query_policy": query_policy,
        "keyword_profile": keyword_profile,
        "vector_profile": vector_profile,
        "keyword_corpus_profile": keyword_corpus_profile,
        "vector_corpus_profile": vector_corpus_profile,
        "doc_profile": doc_profile,
        "diagnostic": diagnostic,
        "case_id": evaluated.case_id,
        "db_id": evaluated.db_id,
        "question": evaluated.question,
        "search_expressions": json.dumps(list(evaluated.search_expressions), ensure_ascii=False),
        "keyword_expressions": json.dumps(list(fused.get("keyword_expressions") or []), ensure_ascii=False),
        "vector_expressions": json.dumps(list(fused.get("vector_expressions") or []), ensure_ascii=False),
        "table_recall_at_5": evaluated.table_recall_at_5,
        "column_recall_at_10": evaluated.column_recall_at_10,
        "mrr_table": evaluated.mrr_table,
        "mrr_column": evaluated.mrr_column,
        "planner_latency_ms": planner_latency_ms,
        "query_embedding_ms": query_embedding_ms,
        "question_embedding_ms": _float_value(fused.get("question_embedding_ms")),
        "expression_embedding_ms": _float_value(fused.get("expression_embedding_ms")),
        "keyword_recall_ms": _float_value(fused.get("keyword_recall_ms")),
        "vector_recall_ms": _float_value(fused.get("vector_recall_ms")),
        "merge_ms": _float_value(fused.get("merge_ms")),
        "multi_fuse_ms": _float_value(fused.get("multi_fuse_ms")),
        "rerank_ms": _float_value(fused.get("rerank_ms")),
        "retrieval_only_ms": retrieval_only_ms,
        "query_preprocess_ms": round(planner_latency_ms + query_embedding_ms, 3),
        "e2e_ms": modeled_online_ms,
        "modeled_online_ms": modeled_online_ms,
        "measured_provider_ms": measured_provider_ms,
        "planner_expression_count": int(_float_value(fused.get("planner_expression_count"))),
        "vector_expression_count": int(_float_value(fused.get("vector_expression_count"))),
        "question_embedding_call_count": int(_float_value(fused.get("question_embedding_call_count"))),
        "expression_embedding_call_count": int(_float_value(fused.get("expression_embedding_call_count"))),
        "embedding_call_count": int(_float_value(fused.get("embedding_call_count"))),
        "vector_available": evaluated.vector_available,
        "db_search_call_count": int(_float_value(fused.get("db_search_call_count")) or evaluated.db_search_call_count),
        "failure_class": evaluated.failure_class,
        "failure_reason": evaluated.failure_reason or "",
    }


def _write_outputs(prep: dict[str, Any], search_plans: list[dict[str, Any]], case_rows: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> None:
    (REPORT_DIR / "prep_check.json").write_text(json.dumps(prep, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_DIR / "search_plans.json").write_text(json.dumps(search_plans, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT_DIR / "contrast_summary.json").write_text(json.dumps({"summaries": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = list(case_rows[0].keys()) if case_rows else []
    with (REPORT_DIR / "contrast_cases.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(case_rows)
    (REPORT_DIR / "contrast_cases.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in case_rows),
        encoding="utf-8",
    )
    (REPORT_DIR / "contrast_report.md").write_text(_markdown_report(summaries), encoding="utf-8")


def _markdown_report(summaries: list[dict[str, Any]]) -> str:
    lines = [
        "# Spider Retrieval Profile Contrast Report",
        "",
        "## Main Recommendation Candidates",
        "",
        "| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | mrr_table | mrr_column | planner expr avg | q-embed calls avg | expr-embed calls avg | db.search calls avg | measured provider p95 | modeled online p95 | query embed p95 | keyword recall p95 | vector recall p95 | vector_available |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    main_rows = [row for row in summaries if not row.get("diagnostic")]
    diagnostic_rows = [row for row in summaries if row.get("diagnostic")]
    for row in main_rows:
        lines.append(
            "| {schema_variant} | {retriever} | {query_mode} | {query_policy} | {keyword_corpus_profile} | "
            "{vector_corpus_profile} | {total_cases} | {table_recall_at_5:.2%} | "
            "{column_recall_at_10:.2%} | {mrr_table:.4f} | {mrr_column:.4f} | "
            "{avg_planner_expression_count} | {avg_question_embedding_call_count} | "
            "{avg_expression_embedding_call_count} | {avg_db_search_call_count} | "
            "{p95_measured_provider_ms} | {p95_modeled_online_ms} | {p95_query_embedding_ms} | "
            "{p95_keyword_recall_ms} | {p95_vector_recall_ms} | {vector_available_rate} |".format(**row)
        )
    if diagnostic_rows:
        lines.extend(
            [
                "",
                "## Diagnostic / Stress Variants",
                "",
                "These rows use `multi_keyword_vector_expression_each`, which embeds every planner expression. They are diagnostic/stress only and are excluded from the main recommendation table.",
                "",
                "| variant | retriever | query_mode | query_policy | keyword corpus | vector corpus | cases | table@5 | column@10 | expr-embed calls avg | measured provider p95 | modeled online p95 | query embed p95 |",
                "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in diagnostic_rows:
            lines.append(
                "| {schema_variant} | {retriever} | {query_mode} | {query_policy} | {keyword_corpus_profile} | "
                "{vector_corpus_profile} | {total_cases} | {table_recall_at_5:.2%} | "
                "{column_recall_at_10:.2%} | {avg_expression_embedding_call_count} | "
                "{p95_measured_provider_ms} | {p95_modeled_online_ms} | {p95_query_embedding_ms} |".format(**row)
            )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Main hybrid policy uses planner expressions for keyword search and embeds the original question once for vector search.",
            "- `multi_keyword_vector_expression_each` embeds every planner expression and is diagnostic/stress only.",
            "- Planner warmup is reported in `prep_check.json` and excluded from per-case planner latency.",
            "- Corpus embedding build is reported in `prep_check.json`, not counted as per-query e2e latency.",
            "- `vector_recall_ms` excludes `query_embedding_ms`; query embedding is reported separately.",
            "- Runs below 100 cases are smoke/directional, not final decision support.",
        ]
    )
    return "\n".join(lines) + "\n"


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
