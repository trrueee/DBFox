from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class ExpectedSchema:
    tables: tuple[str, ...]
    columns: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalHit:
    type: str
    table_name: str
    column_name: str | None = None
    score: float = 0.0
    name: str | None = None
    rank: int | None = None
    keyword_rank: int | None = None
    vector_rank: int | None = None
    matched_by: tuple[str, ...] = ()
    matched_fields: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def key(self) -> tuple[str, str, str | None]:
        return (self.type, self.table_name, self.column_name if self.type == "column" else None)

    @property
    def ref(self) -> str:
        if self.type == "column" and self.column_name:
            return f"{self.table_name}.{self.column_name}"
        return self.table_name

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, rank: int | None = None) -> "RetrievalHit":
        name = str(raw.get("name") or "")
        column_name = raw.get("column_name")
        table_name = raw.get("table_name")
        if not table_name and "." in name:
            table_name = name.split(".", 1)[0]
        if not column_name and "." in name:
            column_name = name.split(".", 1)[1]
        hit_type = str(raw.get("type") or ("column" if column_name else "table")).strip().lower()
        table = _normalize_name(str(table_name or name))
        column = _normalize_name(str(column_name)) if column_name else None
        matched_by = _tuple_of_strings(raw.get("matched_by"))
        matched_fields = tuple(sorted(_tuple_of_strings(raw.get("matched_fields"))))
        try:
            score = float(raw.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return cls(
            type=hit_type,
            table_name=table,
            column_name=column,
            score=score,
            name=name or None,
            rank=rank,
            keyword_rank=_optional_int(raw.get("keyword_rank")),
            vector_rank=_optional_int(raw.get("vector_rank")),
            matched_by=matched_by,
            matched_fields=matched_fields,
            reason=str(raw.get("reason")) if raw.get("reason") else None,
        )


@dataclass(frozen=True)
class CaseEvaluationInput:
    case_id: str
    db_id: str
    variant: str
    question: str
    expected_tables: tuple[str, ...]
    expected_columns: tuple[str, ...]
    retrieved_items: tuple[RetrievalHit, ...]
    search_expressions: tuple[str, ...] = ()
    mode: str = "live"
    actual_sql: str | None = None
    query_execution_success: bool = False
    latency_ms: int = 0
    retrieval_latency_ms: float = 0.0
    embedding_build_time_ms: float = 0.0
    vector_available: bool | None = None
    step_count: int = 0
    tool_call_count: int = 0
    db_search_call_count: int = 0
    schema_observe_count: int = 0
    replan_count: int = 0
    clarification_count: int = 0
    safety_violation_count: int = 0
    answer_grounded: bool | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class CaseEvaluationResult:
    case_id: str
    db_id: str
    variant: str
    mode: str
    question: str
    search_expressions: tuple[str, ...]
    expected_tables: tuple[str, ...]
    retrieved_tables_top5: tuple[str, ...]
    table_recall_at_3: bool
    table_recall_at_5: bool
    expected_columns: tuple[str, ...]
    retrieved_columns_top10: tuple[str, ...]
    column_recall_at_10: bool
    mrr_table: float
    mrr_column: float
    context_precision_at_5: float
    actual_sql: str | None
    used_tables: tuple[str, ...]
    used_columns: tuple[str, ...]
    query_generated: bool
    sql_uses_expected_tables: bool
    sql_uses_expected_columns: bool
    query_execution_success: bool
    answer_grounded: bool
    wrong_table: bool
    missing_key_table: bool
    task_solved: bool
    latency_ms: int
    retrieval_latency_ms: float
    embedding_build_time_ms: float
    vector_available: bool | None
    step_count: int
    tool_call_count: int
    db_search_call_count: int
    schema_observe_count: int
    replan_count: int
    clarification_count: int
    safety_violation_count: int
    failure_class: str
    failure_reason: str | None = None


@dataclass(frozen=True)
class VariantSummary:
    variant: str
    total_cases: int
    table_recall_at_5: float
    column_recall_at_10: float
    task_solve_rate: float
    query_generated_rate: float
    query_execution_success_rate: float
    answer_grounded_rate: float
    wrong_table_rate: float
    missing_key_table_rate: float
    avg_latency_ms: float | None
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    avg_retrieval_latency_ms: float | None
    p50_retrieval_latency_ms: float | None
    p95_retrieval_latency_ms: float | None
    avg_embedding_build_time_ms: float | None
    p50_embedding_build_time_ms: float | None
    p95_embedding_build_time_ms: float | None
    vector_available_rate: float | None
    avg_steps: float
    avg_tool_calls: float
    db_search_call_count: int
    schema_observe_count: int
    replan_count: int
    clarification_count: int
    safety_violations: int
    failure_class_counts: dict[str, int]
    failure_class_rates: dict[str, float]


def extract_expected_schema_from_sql(sql: str, *, dialect: str = "sqlite") -> ExpectedSchema:
    if not sql or not sql.strip():
        return ExpectedSchema(tables=(), columns=())
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return ExpectedSchema(tables=(), columns=())

    aliases: dict[str, str] = {}
    tables: set[str] = set()
    for table in parsed.find_all(exp.Table):
        table_name = _normalize_name(table.name)
        if not table_name:
            continue
        tables.add(table_name)
        aliases[_normalize_name(table.alias_or_name)] = table_name
        aliases[table_name] = table_name

    columns: set[str] = set()
    for column in parsed.find_all(exp.Column):
        column_name = _normalize_name(column.name)
        if not column_name:
            continue
        qualifier = _normalize_name(column.table)
        if qualifier:
            table_name = aliases.get(qualifier, qualifier)
        elif len(tables) == 1:
            table_name = next(iter(tables))
        else:
            continue
        if table_name:
            columns.add(f"{table_name}.{column_name}")

    return ExpectedSchema(tables=tuple(sorted(tables)), columns=tuple(sorted(columns)))


def evaluate_case(payload: CaseEvaluationInput) -> CaseEvaluationResult:
    mode = str(payload.mode or "live").strip().lower().replace("_", "-")
    expected_tables = _normalize_tuple(payload.expected_tables)
    expected_columns = _normalize_tuple(payload.expected_columns)
    hits = tuple(payload.retrieved_items)

    table_top3 = set(_unique_tables(hits[:3]))
    table_top5_tuple = _unique_tables(hits[:5])
    table_top5 = set(table_top5_tuple)
    column_top10_tuple = _unique_columns(hits[:10])
    column_top10 = set(column_top10_tuple)

    expected_table_set = set(expected_tables)
    expected_column_set = set(expected_columns)

    table_recall_at_3 = expected_table_set.issubset(table_top3) if expected_table_set else True
    table_recall_at_5 = expected_table_set.issubset(table_top5) if expected_table_set else True
    column_recall_at_10 = expected_column_set.issubset(column_top10) if expected_column_set else True
    mrr_table = _mrr(hits, lambda hit: hit.table_name in expected_table_set)
    mrr_column = _mrr(hits, lambda hit: hit.ref in expected_column_set)
    context_precision_at_5 = _context_precision(hits[:5], expected_table_set, expected_column_set)

    actual_schema = extract_expected_schema_from_sql(payload.actual_sql or "")
    actual_tables = set(actual_schema.tables)
    actual_columns = set(actual_schema.columns)
    used_tables = tuple(sorted(actual_tables))
    used_columns = tuple(sorted(actual_columns))
    sql_uses_expected_tables = expected_table_set.issubset(actual_tables) if expected_table_set else True
    sql_uses_expected_columns = expected_column_set.issubset(actual_columns) if expected_column_set else True
    query_generated = bool((payload.actual_sql or "").strip())
    retrieval_mode = _is_retrieval_evaluation_mode(mode)
    if retrieval_mode:
        missing_key_table = not table_recall_at_5
        wrong_table = False
    else:
        missing_key_table = not table_recall_at_5 or not sql_uses_expected_tables
        wrong_table = bool(actual_tables - expected_table_set) and not sql_uses_expected_tables
    answer_grounded = bool(payload.answer_grounded) if payload.answer_grounded is not None else payload.query_execution_success
    task_solved = (
        table_recall_at_5
        and sql_uses_expected_tables
        and query_generated
        and payload.query_execution_success
        and answer_grounded
        and payload.safety_violation_count == 0
    )
    if retrieval_mode and table_recall_at_5 and column_recall_at_10 and not payload.failure_reason:
        failure_reason = None
    else:
        failure_reason = payload.failure_reason or _failure_reason(
            task_solved=task_solved,
            missing_key_table=missing_key_table,
            wrong_table=wrong_table,
            query_generated=query_generated,
            query_execution_success=payload.query_execution_success,
            safety_violation_count=payload.safety_violation_count,
            expected_tables=expected_table_set,
            retrieved_tables=table_top5,
            actual_tables=actual_tables,
            mode=mode,
        )
    failure_class = _failure_class(
        mode=mode,
        task_solved=task_solved,
        table_recall_at_5=table_recall_at_5,
        column_recall_at_10=column_recall_at_10,
        query_generated=query_generated,
        query_execution_success=payload.query_execution_success,
        safety_violation_count=payload.safety_violation_count,
        failure_reason=failure_reason,
    )

    return CaseEvaluationResult(
        case_id=payload.case_id,
        db_id=payload.db_id,
        variant=payload.variant,
        mode=mode,
        question=payload.question,
        search_expressions=payload.search_expressions,
        expected_tables=expected_tables,
        retrieved_tables_top5=table_top5_tuple,
        table_recall_at_3=table_recall_at_3,
        table_recall_at_5=table_recall_at_5,
        expected_columns=expected_columns,
        retrieved_columns_top10=column_top10_tuple,
        column_recall_at_10=column_recall_at_10,
        mrr_table=mrr_table,
        mrr_column=mrr_column,
        context_precision_at_5=context_precision_at_5,
        actual_sql=payload.actual_sql,
        used_tables=used_tables,
        used_columns=used_columns,
        query_generated=query_generated,
        sql_uses_expected_tables=sql_uses_expected_tables,
        sql_uses_expected_columns=sql_uses_expected_columns,
        query_execution_success=payload.query_execution_success,
        answer_grounded=answer_grounded,
        wrong_table=wrong_table,
        missing_key_table=missing_key_table,
        task_solved=task_solved,
        latency_ms=payload.latency_ms,
        retrieval_latency_ms=round(payload.retrieval_latency_ms, 3),
        embedding_build_time_ms=round(payload.embedding_build_time_ms, 3),
        vector_available=payload.vector_available,
        step_count=payload.step_count,
        tool_call_count=payload.tool_call_count,
        db_search_call_count=payload.db_search_call_count,
        schema_observe_count=payload.schema_observe_count,
        replan_count=payload.replan_count,
        clarification_count=payload.clarification_count,
        safety_violation_count=payload.safety_violation_count,
        failure_class=failure_class,
        failure_reason=failure_reason,
    )


def summarize_variant(variant: str, results: Iterable[CaseEvaluationResult]) -> VariantSummary:
    rows = tuple(results)
    total = len(rows)
    latencies = [row.latency_ms for row in rows]
    retrieval_latencies = [row.retrieval_latency_ms for row in rows if row.retrieval_latency_ms > 0]
    embedding_times = [row.embedding_build_time_ms for row in rows if row.embedding_build_time_ms > 0]
    vector_availability = [row.vector_available for row in rows if row.vector_available is not None]
    failure_counts: dict[str, int] = {}
    for row in rows:
        failure_counts[row.failure_class] = failure_counts.get(row.failure_class, 0) + 1
    failure_rates = {
        key: round(value / total, 4) if total else 0.0
        for key, value in sorted(failure_counts.items())
    }
    return VariantSummary(
        variant=variant,
        total_cases=total,
        table_recall_at_5=_rate(row.table_recall_at_5 for row in rows),
        column_recall_at_10=_rate(row.column_recall_at_10 for row in rows),
        task_solve_rate=_rate(row.task_solved for row in rows),
        query_generated_rate=_rate(row.query_generated for row in rows),
        query_execution_success_rate=_rate(row.query_execution_success for row in rows),
        answer_grounded_rate=_rate(row.answer_grounded for row in rows),
        wrong_table_rate=_rate(row.wrong_table for row in rows),
        missing_key_table_rate=_rate(row.missing_key_table for row in rows),
        avg_latency_ms=round(sum(latencies) / total, 2) if total else None,
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
        avg_retrieval_latency_ms=round(sum(retrieval_latencies) / len(retrieval_latencies), 3)
        if retrieval_latencies else None,
        p50_retrieval_latency_ms=_percentile_float(retrieval_latencies, 50),
        p95_retrieval_latency_ms=_percentile_float(retrieval_latencies, 95),
        avg_embedding_build_time_ms=round(sum(embedding_times) / len(embedding_times), 3)
        if embedding_times else None,
        p50_embedding_build_time_ms=_percentile_float(embedding_times, 50),
        p95_embedding_build_time_ms=_percentile_float(embedding_times, 95),
        vector_available_rate=round(sum(1 for value in vector_availability if value) / len(vector_availability), 4)
        if vector_availability else None,
        avg_steps=round(sum(row.step_count for row in rows) / total, 2) if total else 0.0,
        avg_tool_calls=round(sum(row.tool_call_count for row in rows) / total, 2) if total else 0.0,
        db_search_call_count=sum(row.db_search_call_count for row in rows),
        schema_observe_count=sum(row.schema_observe_count for row in rows),
        replan_count=sum(row.replan_count for row in rows),
        clarification_count=sum(row.clarification_count for row in rows),
        safety_violations=sum(row.safety_violation_count for row in rows),
        failure_class_counts=dict(sorted(failure_counts.items())),
        failure_class_rates=failure_rates,
    )


def _normalize_name(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip('"`[]').lower()


def _normalize_tuple(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({_normalize_name(value) for value in values if _normalize_name(value)}))


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _unique_tables(hits: Iterable[RetrievalHit]) -> tuple[str, ...]:
    seen: set[str] = set()
    tables: list[str] = []
    for hit in hits:
        table = _normalize_name(hit.table_name)
        if table and table not in seen:
            seen.add(table)
            tables.append(table)
    return tuple(tables)


def _unique_columns(hits: Iterable[RetrievalHit]) -> tuple[str, ...]:
    seen: set[str] = set()
    columns: list[str] = []
    for hit in hits:
        if hit.type != "column" or not hit.column_name:
            continue
        ref = f"{_normalize_name(hit.table_name)}.{_normalize_name(hit.column_name)}"
        if ref not in seen:
            seen.add(ref)
            columns.append(ref)
    return tuple(columns)


def _mrr(hits: Iterable[RetrievalHit], predicate: Any) -> float:
    for index, hit in enumerate(hits, start=1):
        if predicate(hit):
            return round(1.0 / index, 4)
    return 0.0


def _context_precision(
    hits: Iterable[RetrievalHit],
    expected_tables: set[str],
    expected_columns: set[str],
) -> float:
    rows = tuple(hits)
    if not rows:
        return 0.0
    relevant = 0
    for hit in rows:
        if hit.ref in expected_columns or hit.table_name in expected_tables:
            relevant += 1
    return round(relevant / len(rows), 4)


def _rate(values: Iterable[bool]) -> float:
    rows = tuple(values)
    if not rows:
        return 0.0
    return round(sum(1 for value in rows if value) / len(rows), 4)


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return int(round(ordered[lower] * (1 - weight) + ordered[upper] * weight))


def _percentile_float(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _failure_reason(
    *,
    task_solved: bool,
    missing_key_table: bool,
    wrong_table: bool,
    query_generated: bool,
    query_execution_success: bool,
    safety_violation_count: int,
    expected_tables: set[str],
    retrieved_tables: set[str],
    actual_tables: set[str],
    mode: str,
) -> str | None:
    if task_solved:
        return None
    reasons: list[str] = []
    missing_retrieval = sorted(expected_tables - retrieved_tables)
    missing_sql = sorted(expected_tables - actual_tables)
    if missing_key_table and missing_retrieval:
        reasons.append(f"missing expected tables in retrieval: {', '.join(missing_retrieval)}")
    if not _is_retrieval_evaluation_mode(mode) and missing_key_table and missing_sql:
        reasons.append(f"missing expected tables in SQL: {', '.join(missing_sql)}")
    if wrong_table:
        wrong = sorted(actual_tables - expected_tables)
        reasons.append(f"used unexpected tables: {', '.join(wrong)}")
    if not query_generated and not _is_retrieval_evaluation_mode(mode):
        reasons.append("no query generated")
    if query_generated and not query_execution_success:
        reasons.append("query execution failed")
    if safety_violation_count:
        reasons.append(f"safety violations: {safety_violation_count}")
    return "; ".join(reasons) if reasons else "task not solved"


def _failure_class(
    *,
    mode: str,
    task_solved: bool,
    table_recall_at_5: bool,
    column_recall_at_10: bool,
    query_generated: bool,
    query_execution_success: bool,
    safety_violation_count: int,
    failure_reason: str | None,
) -> str:
    if _is_retrieval_evaluation_mode(mode):
        if table_recall_at_5 and column_recall_at_10 and not failure_reason:
            return "none"
        if not table_recall_at_5 or not column_recall_at_10:
            return "retrieval_miss"
    if task_solved:
        return "none"
    text = (failure_reason or "").lower()
    if "unknown tool" in text:
        return "unknown_tool"
    if "policygate" in text or "policy gate" in text or "blocked" in text:
        return "policy_gate_block"
    if "recursion limit" in text or "loop prevention" in text or "repeated with same args" in text:
        return "agent_loop_or_recursion"
    if (
        "ilike" in text
        or "invalid sql identifier" in text
        or "ambiguous column" in text
        or "schema validation parse error" in text
    ):
        return "sql_compatibility"
    if "timeout" in text or "upstream" in text or "connection" in text or "internalservererror" in text:
        return "model_or_infra_error"
    if safety_violation_count:
        return "policy_gate_block"
    if not table_recall_at_5 or not column_recall_at_10:
        return "retrieval_miss"
    if not query_generated:
        return "agent_no_sql"
    if query_generated and not query_execution_success:
        return "query_execution_failed"
    return "unknown"


def _is_retrieval_evaluation_mode(mode: str) -> bool:
    return mode in {"retrieval-only", "ai-assisted-retrieval"}
