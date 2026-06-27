from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable


def summarize_contrast_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row.get("schema_variant") or ""),
                str(row.get("retriever") or ""),
                str(row.get("query_mode") or ""),
            )
        ].append(row)

    summaries: list[dict[str, Any]] = []
    for schema_variant, retriever, query_mode in sorted(grouped):
        items = grouped[(schema_variant, retriever, query_mode)]
        total = len(items)
        vector_values = [
            bool(row.get("vector_available"))
            for row in items
            if row.get("vector_available") is not None
        ]
        failure_counts: dict[str, int] = {}
        for row in items:
            failure_class = str(row.get("failure_class") or "unknown")
            failure_counts[failure_class] = failure_counts.get(failure_class, 0) + 1

        summary = {
            "schema_variant": schema_variant,
            "retriever": retriever,
            "query_mode": query_mode,
            "total_cases": total,
            "table_recall_at_5": _rate(row.get("table_recall_at_5") for row in items),
            "column_recall_at_10": _rate(row.get("column_recall_at_10") for row in items),
            "mrr_table": _avg_float(row.get("mrr_table") for row in items),
            "mrr_column": _avg_float(row.get("mrr_column") for row in items),
            "vector_available_rate": (
                round(sum(1 for value in vector_values if value) / len(vector_values), 4)
                if vector_values
                else None
            ),
            "failure_class_counts": dict(sorted(failure_counts.items())),
        }
        summary.update(_latency_distribution("planner_latency_ms", items))
        summary.update(_latency_distribution("query_embedding_ms", items))
        summary.update(_latency_distribution("retrieval_only_ms", items))
        summary.update(_latency_distribution("merge_ms", items))
        summary.update(_latency_distribution("rerank_ms", items))
        summary.update(_latency_distribution("e2e_ms", items))
        summaries.append(summary)
    return summaries


def _rate(values: Iterable[Any]) -> float:
    items = [bool(value) for value in values]
    if not items:
        return 0.0
    return round(sum(1 for value in items if value) / len(items), 4)


def _avg_float(values: Iterable[Any]) -> float:
    items = [_float_value(value) for value in values]
    if not items:
        return 0.0
    return round(sum(items) / len(items), 4)


def _percentile_float(values: Iterable[float], percentile: int = 95) -> float | None:
    items = sorted(float(value) for value in values)
    if not items:
        return None
    index = max(0, math.ceil((percentile / 100) * len(items)) - 1)
    return round(items[min(index, len(items) - 1)], 3)


def _median_float(values: Iterable[float]) -> float | None:
    items = sorted(float(value) for value in values)
    if not items:
        return None
    midpoint = len(items) // 2
    if len(items) % 2:
        return round(items[midpoint], 3)
    return round((items[midpoint - 1] + items[midpoint]) / 2, 3)


def _max_float(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values]
    if not items:
        return None
    return round(max(items), 3)


def _latency_distribution(field: str, rows: list[dict[str, Any]]) -> dict[str, float | None]:
    values = [_float_value(row.get(field)) for row in rows]
    label = field.removesuffix("_ms")
    return {
        f"p50_{label}_ms": _median_float(values),
        f"p90_{label}_ms": _percentile_float(values, percentile=90),
        f"p95_{label}_ms": _percentile_float(values, percentile=95),
        f"max_{label}_ms": _max_float(values),
    }


def _float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
