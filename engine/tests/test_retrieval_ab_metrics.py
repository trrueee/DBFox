from __future__ import annotations

from engine.evaluation.retrieval_ab.metrics import (
    CaseEvaluationInput,
    RetrievalHit,
    extract_expected_schema_from_sql,
    evaluate_case,
    summarize_variant,
)


def test_extract_expected_schema_from_gold_sql_resolves_aliases() -> None:
    sql = """
        SELECT T1.name
        FROM singer AS T1
        JOIN singer_in_concert AS T2 ON T1.singer_id = T2.singer_id
        JOIN concert AS T3 ON T2.concert_id = T3.concert_id
        WHERE T3.year = 2014
    """

    expected = extract_expected_schema_from_sql(sql)

    assert expected.tables == ("concert", "singer", "singer_in_concert")
    assert expected.columns == (
        "concert.concert_id",
        "concert.year",
        "singer.name",
        "singer.singer_id",
        "singer_in_concert.concert_id",
        "singer_in_concert.singer_id",
    )


def test_evaluate_case_scores_retrieval_sql_and_task_solution() -> None:
    result = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_concert_singer_001",
            db_id="concert_singer",
            variant="hybrid",
            question="Which singers performed in 2014?",
            expected_tables=("singer", "concert"),
            expected_columns=("singer.name", "concert.year"),
            retrieved_items=(
                RetrievalHit(type="table", table_name="singer", score=9.0),
                RetrievalHit(type="column", table_name="singer", column_name="name", score=8.0),
                RetrievalHit(type="table", table_name="concert", score=7.0),
                RetrievalHit(type="column", table_name="concert", column_name="year", score=6.0),
            ),
            actual_sql=(
                "SELECT singer.name FROM singer "
                "JOIN singer_in_concert ON singer.singer_id = singer_in_concert.singer_id "
                "JOIN concert ON singer_in_concert.concert_id = concert.concert_id "
                "WHERE concert.year = 2014"
            ),
            query_execution_success=True,
            latency_ms=9200,
            step_count=6,
            tool_call_count=4,
            db_search_call_count=1,
        )
    )

    assert result.table_recall_at_3 is True
    assert result.table_recall_at_5 is True
    assert result.column_recall_at_10 is True
    assert result.mrr_table == 1.0
    assert result.mrr_column == 0.5
    assert result.context_precision_at_5 == 1.0
    assert result.sql_uses_expected_tables is True
    assert result.sql_uses_expected_columns is True
    assert result.query_execution_success is True
    assert result.task_solved is True


def test_evaluate_case_reports_missing_key_tables_and_wrong_tables() -> None:
    result = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_pets_1_001",
            db_id="pets_1",
            variant="keyword",
            question="How many students have pets?",
            expected_tables=("students", "has_pet"),
            expected_columns=("students.stuid", "has_pet.stuid"),
            retrieved_items=(
                RetrievalHit(type="table", table_name="pets", score=5.0),
                RetrievalHit(type="column", table_name="pets", column_name="petid", score=4.0),
            ),
            actual_sql="SELECT COUNT(*) FROM pets",
            query_execution_success=True,
            latency_ms=1200,
        )
    )

    assert result.table_recall_at_5 is False
    assert result.column_recall_at_10 is False
    assert result.missing_key_table is True
    assert result.wrong_table is True
    assert result.task_solved is False
    assert "missing expected tables" in str(result.failure_reason)


def test_retrieval_only_case_marks_none_when_expected_schema_is_retrieved() -> None:
    result = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_tiny_school_001",
            db_id="tiny_school",
            variant="keyword",
            mode="retrieval-only",
            question="How many students are there?",
            expected_tables=("students",),
            expected_columns=("students.id",),
            retrieved_items=(
                RetrievalHit(type="table", table_name="students", score=10.0),
                RetrievalHit(type="column", table_name="students", column_name="id", score=9.0),
            ),
        )
    )

    assert result.failure_class == "none"
    assert result.failure_reason is None
    assert result.used_tables == ()
    assert result.used_columns == ()
    assert result.missing_key_table is False
    assert result.wrong_table is False
    assert result.task_solved is False


def test_retrieval_only_case_marks_retrieval_miss_when_expected_table_is_absent() -> None:
    result = evaluate_case(
        CaseEvaluationInput(
            case_id="spider_tiny_school_002",
            db_id="tiny_school",
            variant="vector",
            mode="retrieval-only",
            question="How many students are there?",
            expected_tables=("students",),
            expected_columns=("students.id",),
            retrieved_items=(RetrievalHit(type="table", table_name="teachers", score=10.0),),
        )
    )

    assert result.failure_class == "retrieval_miss"
    assert "missing expected tables in retrieval: students" in str(result.failure_reason)


def test_summarize_variant_aggregates_rates_and_latency_percentiles() -> None:
    passing = evaluate_case(
        CaseEvaluationInput(
            case_id="case_pass",
            db_id="db",
            variant="keyword",
            question="q",
            expected_tables=("orders",),
            expected_columns=("orders.id",),
            retrieved_items=(
                RetrievalHit(type="table", table_name="orders", score=3.0),
                RetrievalHit(type="column", table_name="orders", column_name="id", score=2.0),
            ),
            actual_sql="SELECT orders.id FROM orders",
            query_execution_success=True,
            latency_ms=100,
            step_count=2,
            tool_call_count=2,
            db_search_call_count=1,
        )
    )
    failing = evaluate_case(
        CaseEvaluationInput(
            case_id="case_fail",
            db_id="db",
            variant="keyword",
            question="q",
            expected_tables=("customers",),
            expected_columns=("customers.id",),
            retrieved_items=(RetrievalHit(type="table", table_name="orders", score=3.0),),
            actual_sql="SELECT orders.id FROM orders",
            query_execution_success=False,
            latency_ms=300,
            step_count=4,
            tool_call_count=3,
            db_search_call_count=1,
            safety_violation_count=1,
        )
    )

    summary = summarize_variant("keyword", (passing, failing))

    assert summary.total_cases == 2
    assert summary.table_recall_at_5 == 0.5
    assert summary.column_recall_at_10 == 0.5
    assert summary.task_solve_rate == 0.5
    assert summary.query_execution_success_rate == 0.5
    assert summary.p50_latency_ms == 200
    assert summary.p95_latency_ms == 290
    assert summary.avg_steps == 3.0
    assert summary.safety_violations == 1
