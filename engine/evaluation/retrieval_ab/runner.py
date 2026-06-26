from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from engine.evaluation.retrieval_ab.metrics import (
    CaseEvaluationInput,
    CaseEvaluationResult,
    RetrievalHit,
    evaluate_case,
    summarize_variant,
)
from engine.evaluation.retrieval_ab.spider_fixture import EvaluationCase


@dataclass(frozen=True)
class AgentRunArtifacts:
    actual_sql: str | None
    query_execution_success: bool
    events: tuple[dict[str, Any], ...] = ()
    latency_ms: int = 0
    error: str | None = None
    answer_grounded: bool | None = None


@dataclass(frozen=True)
class DbSearchTraceMetrics:
    retrieval_latency_ms: float = 0.0
    embedding_build_time_ms: float = 0.0
    vector_available: bool | None = None


RunCaseFn = Callable[[EvaluationCase, str], AgentRunArtifacts]


class RetrievalAbRunner:
    def __init__(self, run_case: RunCaseFn) -> None:
        self._run_case = run_case

    def run(
        self,
        cases: Iterable[EvaluationCase],
        *,
        variants: Iterable[str],
    ) -> tuple[tuple[CaseEvaluationResult, ...], tuple[Any, ...]]:
        results: list[CaseEvaluationResult] = []
        case_rows = tuple(cases)
        variant_names = tuple(variants)
        for variant in variant_names:
            for case in case_rows:
                artifacts = self._run_case(case, variant)
                results.append(evaluate_artifacts(case, variant, artifacts))
        summaries = tuple(
            summarize_variant(variant, (row for row in results if row.variant == variant))
            for variant in variant_names
        )
        return tuple(results), summaries


def evaluate_artifacts(
    case: EvaluationCase,
    variant: str,
    artifacts: AgentRunArtifacts,
    *,
    mode: str = "live",
) -> CaseEvaluationResult:
    events = tuple(artifacts.events)
    search_metrics = collect_db_search_metrics(events)
    return evaluate_case(
        CaseEvaluationInput(
            case_id=case.case_id,
            db_id=case.db_id,
            variant=variant,
            mode=mode,
            question=case.question,
            search_expressions=collect_search_expressions(events),
            expected_tables=case.expected_tables,
            expected_columns=case.expected_columns,
            retrieved_items=collect_db_search_results(events),
            actual_sql=artifacts.actual_sql,
            query_execution_success=artifacts.query_execution_success,
            latency_ms=artifacts.latency_ms,
            retrieval_latency_ms=search_metrics.retrieval_latency_ms,
            embedding_build_time_ms=search_metrics.embedding_build_time_ms,
            vector_available=search_metrics.vector_available,
            step_count=count_steps(events),
            tool_call_count=count_tool_calls(events),
            db_search_call_count=count_tool_calls(events, "db.search"),
            schema_observe_count=count_tool_calls(events, "schema.observe"),
            replan_count=count_named_events(events, "replan"),
            clarification_count=count_named_events(events, "clarification"),
            safety_violation_count=count_safety_violations(events),
            answer_grounded=artifacts.answer_grounded,
            failure_reason=artifacts.error,
        )
    )


def collect_db_search_results(events: Iterable[dict[str, Any]]) -> tuple[RetrievalHit, ...]:
    fused_hits = _collect_tool_results(events, "db.search.fused")
    if fused_hits:
        return fused_hits
    return _collect_tool_results(events, "db.search")


def _collect_tool_results(events: Iterable[dict[str, Any]], tool_name: str) -> tuple[RetrievalHit, ...]:
    hits: list[RetrievalHit] = []
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        if _tool_name(step) != tool_name:
            continue
        output = step.get("output")
        if not isinstance(output, dict):
            continue
        results = output.get("results")
        if not isinstance(results, list):
            continue
        for raw in results:
            if isinstance(raw, dict):
                hits.append(RetrievalHit.from_mapping(raw, rank=len(hits) + 1))
    return tuple(hits)


def collect_search_expressions(events: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        if _tool_name(step) not in {"search.plan", "db.search.fused"}:
            continue
        output = step.get("output")
        if not isinstance(output, dict):
            continue
        expressions = output.get("search_expressions")
        if isinstance(expressions, list):
            return tuple(str(item) for item in expressions if str(item).strip())
    return ()


def collect_db_search_metrics(events: Iterable[dict[str, Any]]) -> DbSearchTraceMetrics:
    retrieval_latency_ms = 0.0
    embedding_build_time_ms = 0.0
    vector_values: list[bool] = []
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        if _tool_name(step) not in {"db.search", "schema.embedding.prewarm"}:
            continue
        output = step.get("output")
        if not isinstance(output, dict):
            continue
        retrieval_latency_ms += _float_value(output.get("retrieval_latency_ms"))
        embedding_build_time_ms += _float_value(output.get("embedding_build_time_ms"))
        vector_available = output.get("vector_available")
        if isinstance(vector_available, bool):
            vector_values.append(vector_available)

    vector_available_result = None
    if vector_values:
        vector_available_result = all(vector_values)
    return DbSearchTraceMetrics(
        retrieval_latency_ms=round(retrieval_latency_ms, 3),
        embedding_build_time_ms=round(embedding_build_time_ms, 3),
        vector_available=vector_available_result,
    )


def count_tool_calls(events: Iterable[dict[str, Any]], tool_name: str | None = None) -> int:
    count = 0
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        name = _tool_name(step)
        if not name:
            continue
        if tool_name is None or name == tool_name:
            count += 1
    return count


def count_steps(events: Iterable[dict[str, Any]]) -> int:
    return sum(1 for event in events if isinstance(event.get("step"), dict))


def count_named_events(events: Iterable[dict[str, Any]], name_fragment: str) -> int:
    needle = name_fragment.lower()
    count = 0
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        haystack = " ".join(str(step.get(key) or "") for key in ("tool_name", "name", "event", "type"))
        if needle in haystack.lower():
            count += 1
    return count


def count_safety_violations(events: Iterable[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        step = event.get("step")
        if not isinstance(step, dict):
            continue
        output = step.get("output")
        if isinstance(output, dict):
            for key in ("safety_violation_count", "dangerous_sql_count", "non_select_sql_count"):
                value = output.get(key)
                if isinstance(value, int):
                    total += value
            if output.get("safety_violation") is True:
                total += 1
    return total


def _tool_name(step: dict[str, Any]) -> str:
    return str(step.get("tool_name") or step.get("name") or "").strip()


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
