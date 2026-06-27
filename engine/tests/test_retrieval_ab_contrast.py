from engine.evaluation.retrieval_ab.contrast import summarize_contrast_rows
from engine.evaluation.spider.spider_loader import SpiderExample


def _example(db_id: str, question: str) -> SpiderExample:
    from pathlib import Path

    return SpiderExample(
        db_id=db_id,
        question=question,
        gold_sql="SELECT 1",
        db_path=Path(f"{db_id}.sqlite"),
    )


def test_progress_writer_streams_jsonl_events(tmp_path) -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import ProgressWriter

    path = tmp_path / "progress_events.jsonl"
    writer = ProgressWriter(path, stdout=False)

    writer.emit("run_start", case_count=2)
    writer.emit("case_done", case_id="c1", schema_variant="base")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"event": "run_start"' in lines[0]
    assert '"case_count": 2' in lines[0]
    assert '"event": "case_done"' in lines[1]
    assert '"schema_variant": "base"' in lines[1]
    assert '"ts":' in lines[0]


def test_select_examples_can_use_head_sampling() -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import _select_examples

    examples = (
        _example("a", "a1"),
        _example("a", "a2"),
        _example("b", "b1"),
    )

    selected = _select_examples(examples, limit=2, sample_strategy="head")

    assert [example.question for example in selected] == ["a1", "a2"]


def test_select_examples_can_round_robin_across_limited_dbs() -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import _select_examples

    examples = (
        _example("a", "a1"),
        _example("a", "a2"),
        _example("a", "a3"),
        _example("b", "b1"),
        _example("b", "b2"),
        _example("c", "c1"),
        _example("c", "c2"),
    )

    selected = _select_examples(examples, limit=5, sample_strategy="round_robin_db", db_limit=2)

    assert [example.question for example in selected] == ["a1", "b1", "a2", "b2", "a3"]


def test_default_eval_variants_cover_raw_and_enriched_single_methods_and_hybrids() -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import (
        resolve_eval_variants,
    )

    variants = resolve_eval_variants(())

    assert [(item.name, item.retriever, item.keyword_profile, item.vector_profile, item.corpus_profile) for item in variants] == [
        ("keyword_raw", "keyword", "raw", "none", "raw"),
        ("vector_raw", "vector", "none", "raw", "raw"),
        ("keyword_enriched", "keyword", "enriched", "none", "enriched"),
        ("vector_enriched", "vector", "none", "enriched", "enriched"),
        ("hybrid_raw", "hybrid", "raw", "raw", "raw"),
        ("hybrid_enriched", "hybrid", "enriched", "enriched", "enriched"),
    ]


def test_eval_variant_rejects_ambiguous_legacy_schema_variant_names() -> None:
    import pytest

    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import (
        resolve_eval_variants,
    )

    with pytest.raises(RuntimeError, match="keyword_raw"):
        resolve_eval_variants(("base", "ai_enriched"))


def test_eval_variant_selects_prepared_corpus_datasource() -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import (
        datasource_for_variant,
        resolve_eval_variants,
    )

    corpus_by_db = {"concert_singer": {"raw": "raw-ds", "enriched": "enriched-ds"}}
    variants = {variant.name: variant for variant in resolve_eval_variants(())}

    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["keyword_raw"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["vector_raw"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_raw"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["keyword_enriched"]) == "enriched-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["vector_enriched"]) == "enriched-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_enriched"]) == "enriched-ds"


def test_planner_warmup_is_reported_separately_from_case_plans(tmp_path) -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import (
        ProgressWriter,
        run_planner_warmup,
    )

    calls: list[str] = []
    writer = ProgressWriter(tmp_path / "progress.jsonl", stdout=False)

    result = run_planner_warmup(lambda: calls.append("warm"), writer)
    writer.close()

    assert calls == ["warm"]
    assert result["planner_warmup_ms"] >= 0
    assert result["planner_warmup_in_case_latency"] is False
    assert "planner_warmup_done" in (tmp_path / "progress.jsonl").read_text(encoding="utf-8")


def test_summarize_contrast_rows_groups_quality_and_staged_latency() -> None:
    rows = [
        {
            "schema_variant": "base",
            "retriever": "keyword",
            "query_mode": "multi",
            "table_recall_at_5": True,
            "column_recall_at_10": False,
            "mrr_table": 1.0,
            "mrr_column": 0.0,
            "planner_latency_ms": 900.0,
            "query_embedding_ms": 0.0,
            "retrieval_only_ms": 20.0,
            "merge_ms": 2.0,
            "rerank_ms": 0.0,
            "e2e_ms": 920.0,
            "failure_class": "retrieval_miss",
            "vector_available": None,
        },
        {
            "schema_variant": "base",
            "retriever": "keyword",
            "query_mode": "multi",
            "table_recall_at_5": True,
            "column_recall_at_10": True,
            "mrr_table": 1.0,
            "mrr_column": 1.0,
            "planner_latency_ms": 1100.0,
            "query_embedding_ms": 0.0,
            "retrieval_only_ms": 30.0,
            "merge_ms": 3.0,
            "rerank_ms": 0.0,
            "e2e_ms": 1130.0,
            "failure_class": "none",
            "vector_available": None,
        },
        {
            "schema_variant": "ai_enriched",
            "retriever": "vector",
            "query_mode": "single",
            "table_recall_at_5": False,
            "column_recall_at_10": True,
            "mrr_table": 0.0,
            "mrr_column": 0.5,
            "planner_latency_ms": 0.0,
            "query_embedding_ms": 1200.0,
            "retrieval_only_ms": 1300.0,
            "merge_ms": 0.0,
            "rerank_ms": 0.0,
            "e2e_ms": 1300.0,
            "failure_class": "retrieval_miss",
            "vector_available": True,
        },
    ]

    summaries = summarize_contrast_rows(rows)

    assert summaries[0]["schema_variant"] == "ai_enriched"
    assert summaries[0]["retriever"] == "vector"
    assert summaries[0]["query_mode"] == "single"
    assert summaries[0]["table_recall_at_5"] == 0.0
    assert summaries[0]["column_recall_at_10"] == 1.0
    assert summaries[0]["mrr_column"] == 0.5
    assert summaries[0]["p95_query_embedding_ms"] == 1200.0
    assert summaries[0]["p95_e2e_ms"] == 1300.0
    assert summaries[0]["vector_available_rate"] == 1.0
    assert summaries[0]["failure_class_counts"] == {"retrieval_miss": 1}

    assert summaries[1]["schema_variant"] == "base"
    assert summaries[1]["retriever"] == "keyword"
    assert summaries[1]["query_mode"] == "multi"
    assert summaries[1]["total_cases"] == 2
    assert summaries[1]["table_recall_at_5"] == 1.0
    assert summaries[1]["column_recall_at_10"] == 0.5
    assert summaries[1]["mrr_column"] == 0.5
    assert summaries[1]["p95_planner_latency_ms"] == 1100.0
    assert summaries[1]["p50_planner_latency_ms"] == 1000.0
    assert summaries[1]["p90_planner_latency_ms"] == 1100.0
    assert summaries[1]["max_planner_latency_ms"] == 1100.0
    assert summaries[1]["p95_retrieval_only_ms"] == 30.0
    assert summaries[1]["p50_retrieval_only_ms"] == 25.0
    assert summaries[1]["p90_retrieval_only_ms"] == 30.0
    assert summaries[1]["max_retrieval_only_ms"] == 30.0
    assert summaries[1]["p95_e2e_ms"] == 1130.0
    assert summaries[1]["p50_e2e_ms"] == 1025.0
    assert summaries[1]["p90_e2e_ms"] == 1130.0
    assert summaries[1]["max_e2e_ms"] == 1130.0
    assert summaries[1]["vector_available_rate"] is None
    assert summaries[1]["failure_class_counts"] == {"none": 1, "retrieval_miss": 1}
