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

    assert [(item.name, item.retriever, item.keyword_profile, item.vector_profile, item.keyword_corpus_profile, item.vector_corpus_profile, item.query_policy, item.diagnostic) for item in variants] == [
        ("keyword_raw", "keyword", "raw", "none", "raw", "none", "multi_keyword_vector_question", False),
        ("vector_raw", "vector", "none", "raw", "none", "raw", "single_question", False),
        ("keyword_enriched", "keyword", "enriched", "none", "enriched", "none", "multi_keyword_vector_question", False),
        ("vector_enriched", "vector", "none", "enriched", "none", "enriched", "single_question", False),
        ("hybrid_raw_question", "hybrid", "raw", "raw", "raw", "raw", "multi_keyword_vector_question", False),
        ("hybrid_keyword_enriched_vector_raw_question", "hybrid", "enriched", "raw", "enriched", "raw", "multi_keyword_vector_question", False),
        ("hybrid_keyword_raw_vector_enriched_question", "hybrid", "raw", "enriched", "raw", "enriched", "multi_keyword_vector_question", False),
        ("hybrid_enriched_question", "hybrid", "enriched", "enriched", "enriched", "enriched", "multi_keyword_vector_question", False),
    ]


def test_diagnostic_expression_each_variants_are_opt_in_and_marked() -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import (
        resolve_eval_variants,
    )

    variants = resolve_eval_variants(("hybrid_keyword_enriched_vector_raw_expression_each",))

    assert len(variants) == 1
    assert variants[0].query_policy == "multi_keyword_vector_expression_each"
    assert variants[0].diagnostic is True


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
        vector_datasource_for_variant,
        resolve_eval_variants,
    )

    corpus_by_db = {"concert_singer": {"raw": "raw-ds", "enriched": "enriched-ds"}}
    variants = {variant.name: variant for variant in resolve_eval_variants(())}

    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["keyword_raw"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["vector_raw"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_raw_question"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["keyword_enriched"]) == "enriched-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["vector_enriched"]) == "enriched-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_enriched_question"]) == "enriched-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_keyword_enriched_vector_raw_question"]) == "enriched-ds"
    assert vector_datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_keyword_enriched_vector_raw_question"]) == "raw-ds"
    assert datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_keyword_raw_vector_enriched_question"]) == "raw-ds"
    assert vector_datasource_for_variant(corpus_by_db, "concert_singer", variants["hybrid_keyword_raw_vector_enriched_question"]) == "enriched-ds"


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
            "question_embedding_ms": 0.0,
            "expression_embedding_ms": 0.0,
            "keyword_recall_ms": 20.0,
            "vector_recall_ms": 0.0,
            "retrieval_only_ms": 20.0,
            "merge_ms": 2.0,
            "rerank_ms": 0.0,
            "e2e_ms": 920.0,
            "modeled_online_ms": 920.0,
            "measured_provider_ms": 900.0,
            "query_policy": "multi_keyword_vector_question",
            "keyword_corpus_profile": "raw",
            "vector_corpus_profile": "none",
            "planner_expression_count": 2,
            "question_embedding_call_count": 0,
            "expression_embedding_call_count": 0,
            "embedding_call_count": 0,
            "db_search_call_count": 2,
            "diagnostic": False,
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
            "question_embedding_ms": 0.0,
            "expression_embedding_ms": 0.0,
            "keyword_recall_ms": 30.0,
            "vector_recall_ms": 0.0,
            "retrieval_only_ms": 30.0,
            "merge_ms": 3.0,
            "rerank_ms": 0.0,
            "e2e_ms": 1130.0,
            "modeled_online_ms": 1130.0,
            "measured_provider_ms": 1100.0,
            "query_policy": "multi_keyword_vector_question",
            "keyword_corpus_profile": "raw",
            "vector_corpus_profile": "none",
            "planner_expression_count": 2,
            "question_embedding_call_count": 0,
            "expression_embedding_call_count": 0,
            "embedding_call_count": 0,
            "db_search_call_count": 2,
            "diagnostic": False,
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
            "question_embedding_ms": 1200.0,
            "expression_embedding_ms": 0.0,
            "keyword_recall_ms": 0.0,
            "vector_recall_ms": 100.0,
            "retrieval_only_ms": 1300.0,
            "merge_ms": 0.0,
            "rerank_ms": 0.0,
            "e2e_ms": 1300.0,
            "modeled_online_ms": 1300.0,
            "measured_provider_ms": 1200.0,
            "query_policy": "single_question",
            "keyword_corpus_profile": "none",
            "vector_corpus_profile": "enriched",
            "planner_expression_count": 0,
            "question_embedding_call_count": 1,
            "expression_embedding_call_count": 0,
            "embedding_call_count": 1,
            "db_search_call_count": 1,
            "diagnostic": False,
            "failure_class": "retrieval_miss",
            "vector_available": True,
        },
    ]

    summaries = summarize_contrast_rows(rows)

    assert summaries[0]["schema_variant"] == "ai_enriched"
    assert summaries[0]["retriever"] == "vector"
    assert summaries[0]["query_mode"] == "single"
    assert summaries[0]["query_policy"] == "single_question"
    assert summaries[0]["keyword_corpus_profile"] == "none"
    assert summaries[0]["vector_corpus_profile"] == "enriched"
    assert summaries[0]["table_recall_at_5"] == 0.0
    assert summaries[0]["column_recall_at_10"] == 1.0
    assert summaries[0]["mrr_column"] == 0.5
    assert summaries[0]["p95_query_embedding_ms"] == 1200.0
    assert summaries[0]["p95_question_embedding_ms"] == 1200.0
    assert summaries[0]["p95_expression_embedding_ms"] == 0.0
    assert summaries[0]["avg_question_embedding_call_count"] == 1.0
    assert summaries[0]["avg_expression_embedding_call_count"] == 0.0
    assert summaries[0]["avg_embedding_call_count"] == 1.0
    assert summaries[0]["avg_db_search_call_count"] == 1.0
    assert summaries[0]["p95_modeled_online_ms"] == 1300.0
    assert summaries[0]["p95_measured_provider_ms"] == 1200.0
    assert summaries[0]["p95_e2e_ms"] == 1300.0
    assert summaries[0]["vector_available_rate"] == 1.0
    assert summaries[0]["failure_class_counts"] == {"retrieval_miss": 1}

    assert summaries[1]["schema_variant"] == "base"
    assert summaries[1]["retriever"] == "keyword"
    assert summaries[1]["query_mode"] == "multi"
    assert summaries[1]["query_policy"] == "multi_keyword_vector_question"
    assert summaries[1]["total_cases"] == 2
    assert summaries[1]["table_recall_at_5"] == 1.0
    assert summaries[1]["column_recall_at_10"] == 0.5
    assert summaries[1]["mrr_column"] == 0.5
    assert summaries[1]["p95_planner_latency_ms"] == 1100.0
    assert summaries[1]["p50_planner_latency_ms"] == 1000.0
    assert summaries[1]["p90_planner_latency_ms"] == 1100.0
    assert summaries[1]["max_planner_latency_ms"] == 1100.0
    assert summaries[1]["p95_retrieval_only_ms"] == 30.0
    assert summaries[1]["p95_keyword_recall_ms"] == 30.0
    assert summaries[1]["p50_keyword_recall_ms"] == 25.0
    assert summaries[1]["p95_vector_recall_ms"] == 0.0
    assert summaries[1]["avg_planner_expression_count"] == 2.0
    assert summaries[1]["avg_expression_embedding_call_count"] == 0.0
    assert summaries[1]["avg_db_search_call_count"] == 2.0
    assert summaries[1]["p50_retrieval_only_ms"] == 25.0
    assert summaries[1]["p90_retrieval_only_ms"] == 30.0
    assert summaries[1]["max_retrieval_only_ms"] == 30.0
    assert summaries[1]["p95_e2e_ms"] == 1130.0
    assert summaries[1]["p50_e2e_ms"] == 1025.0
    assert summaries[1]["p90_e2e_ms"] == 1130.0
    assert summaries[1]["max_e2e_ms"] == 1130.0
    assert summaries[1]["vector_available_rate"] is None
    assert summaries[1]["failure_class_counts"] == {"none": 1, "retrieval_miss": 1}


def test_markdown_report_excludes_diagnostic_rows_from_main_recommendation_table() -> None:
    from reports.retrieval_ab_ai_enrich_contrast.run_spider_ai_enrich_contrast import _markdown_report

    base_row = {
        "schema_variant": "hybrid_keyword_enriched_vector_raw_question",
        "retriever": "hybrid",
        "query_mode": "multi",
        "query_policy": "multi_keyword_vector_question",
        "keyword_corpus_profile": "enriched",
        "vector_corpus_profile": "raw",
        "diagnostic": False,
        "total_cases": 6,
        "table_recall_at_5": 1.0,
        "column_recall_at_10": 0.8,
        "mrr_table": 0.9,
        "mrr_column": 0.5,
        "avg_planner_expression_count": 3.0,
        "avg_question_embedding_call_count": 1.0,
        "avg_expression_embedding_call_count": 0.0,
        "avg_db_search_call_count": 4.0,
        "p95_measured_provider_ms": 1400.0,
        "p95_modeled_online_ms": 1500.0,
        "p95_query_embedding_ms": 450.0,
        "p95_keyword_recall_ms": 20.0,
        "p95_vector_recall_ms": 40.0,
        "vector_available_rate": 1.0,
    }
    diagnostic_row = {
        **base_row,
        "schema_variant": "hybrid_keyword_enriched_vector_raw_expression_each",
        "query_policy": "multi_keyword_vector_expression_each",
        "diagnostic": True,
        "avg_expression_embedding_call_count": 3.0,
    }

    md = _markdown_report([base_row, diagnostic_row])
    main, diagnostic = md.split("## Diagnostic / Stress Variants")

    assert "hybrid_keyword_enriched_vector_raw_question" in main
    assert "hybrid_keyword_enriched_vector_raw_expression_each" not in main
    assert "diagnostic/stress only" in diagnostic.lower()
    assert "hybrid_keyword_enriched_vector_raw_expression_each" in diagnostic
