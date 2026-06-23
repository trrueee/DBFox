from __future__ import annotations

from collections import defaultdict
from typing import Any


SUPPORTED_CHART_TYPES = {"line", "bar", "area", "scatter", "pie", "table"}


def suggest_plotly_chart(execution: dict[str, Any] | None) -> dict[str, Any]:
    """Return a safe chart suggestion with optional Plotly-ready series.

    This function is deterministic and only reads query results. It does not
    execute model-generated code and it does not return frontend UI code.
    """
    if not execution or not execution.get("success"):
        return {"type": "table", "x": None, "y": None, "series": [], "reason": "No successful result set is available."}

    columns = [str(item) for item in _list_value(execution.get("columns"))]
    rows = [item for item in _list_value(execution.get("rows")) if isinstance(item, dict)]
    if not columns or not rows:
        return {"type": "table", "x": None, "y": None, "series": [], "reason": "Empty result sets are best displayed as a table."}

    numeric_cols = [column for column in columns if any(_is_number(row.get(column)) for row in rows)]
    time_cols = [column for column in columns if _looks_temporal(column, [row.get(column) for row in rows])]
    category_cols = [column for column in columns if column not in numeric_cols]

    if time_cols and numeric_cols:
        x_col = time_cols[0]
        y_col = numeric_cols[0]
        series = _series_from_rows(rows, x_col, y_col, aggregate=True, max_points=120)
        return {
            "type": "line",
            "x": x_col,
            "y": y_col,
            "title": f"{y_col} by {x_col}",
            "series": series,
            "reason": "A temporal field plus a numeric measure is best shown as a line chart.",
            **_chart_metadata(x_col, y_col, x_kind="temporal", aggregate=True, sample_size=len(rows), data_label=len(series) <= 12),
        }

    if category_cols and numeric_cols:
        x_col = category_cols[0]
        y_col = numeric_cols[0]
        series = _series_from_rows(rows, x_col, y_col, aggregate=True, max_points=120)
        chart_type = "pie" if _looks_like_share(y_col) and 0 < len(series) <= 8 else "bar"
        return {
            "type": chart_type,
            "x": x_col,
            "y": y_col,
            "title": f"{y_col} by {x_col}",
            "series": series,
            "reason": "A category field plus a numeric measure is best compared by category.",
            **_chart_metadata(x_col, y_col, x_kind="category", aggregate=True, sample_size=len(rows), data_label=len(series) <= 24),
        }

    if len(numeric_cols) >= 2:
        x_col = numeric_cols[0]
        y_col = numeric_cols[1]
        return {
            "type": "scatter",
            "x": x_col,
            "y": y_col,
            "title": f"{y_col} vs {x_col}",
            "series": _series_from_rows(rows, x_col, y_col, aggregate=False, max_points=120),
            "reason": "Two numeric fields are best inspected with a scatter-style comparison.",
            **_chart_metadata(x_col, y_col, x_kind="numeric", aggregate=False, sample_size=len(rows), data_label=False),
        }

    return {
        "type": "table",
        "x": columns[0],
        "y": numeric_cols[0] if numeric_cols else None,
        "series": [],
        "reason": "No clear category/time plus numeric pairing was found.",
        "sample_size": len(rows),
    }


def _series_from_rows(rows: list[dict[str, Any]], x_col: str, y_col: str, *, aggregate: bool, max_points: int) -> list[dict[str, Any]]:
    if not aggregate:
        points: list[dict[str, Any]] = []
        for row in rows[:max_points]:
            value = _to_number(row.get(y_col))
            label = _format_label(row.get(x_col))
            if label is None or value is None:
                continue
            points.append({"label": label, "value": value})
        return points

    grouped: dict[str, float] = defaultdict(float)
    for row in rows:
        value = _to_number(row.get(y_col))
        label = _format_label(row.get(x_col))
        if label is None or value is None:
            continue
        grouped[label] += value

    return [
        {"label": label, "value": value}
        for label, value in list(grouped.items())[:max_points]
    ]


def _chart_metadata(
    x_col: str,
    y_col: str,
    *,
    x_kind: str,
    aggregate: bool,
    sample_size: int,
    data_label: bool,
) -> dict[str, Any]:
    aggregation = "sum" if aggregate else "none"
    expression = f"SUM({y_col})" if aggregate else y_col
    return {
        "x_label": x_col,
        "y_label": y_col,
        "series_label": y_col,
        "aggregation": aggregation,
        "data_label": data_label,
        "sample_size": sample_size,
        "dimensions": [
            {
                "name": x_col,
                "column": x_col,
                "role": "x",
                "kind": x_kind,
            }
        ],
        "metrics": [
            {
                "name": y_col,
                "source_column": y_col,
                "expression": expression,
                "aggregation": aggregation,
                "role": "y",
            }
        ],
    }


def _looks_temporal(column: str, values: list[Any]) -> bool:
    lower = column.lower()
    if any(token in lower for token in ["date", "time", "created", "updated", "day", "week", "month", "year", "日期", "时间", "周", "月", "年"]):
        return True
    samples = [str(v) for v in values[:8] if v is not None]
    return any("-" in item and len(item) >= 7 for item in samples)


def _looks_like_share(column: str) -> bool:
    lower = column.lower()
    return any(token in lower for token in ["rate", "ratio", "share", "percent", "pct", "占比", "比例", "%"])


def _is_number(value: Any) -> bool:
    return _to_number(value) is not None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _format_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
