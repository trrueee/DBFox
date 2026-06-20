from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from engine.agent_core.types import ColumnProfile, ResultProfile


def profile_result(
    question: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    query_plan: dict[str, Any] | None = None,
    execution_success: bool = True,
) -> ResultProfile:
    row_count = len(rows)
    if not execution_success:
        return ResultProfile(
            row_count=0,
            detected_patterns=["execution_skipped"],
            notable_facts=["查询未执行或被跳过，没有可分析的结果集。"],
            limitations=["本次没有返回结果集，因此无法生成结果画像。"],
        )

    if row_count == 0:
        return ResultProfile(
            row_count=0,
            detected_patterns=["empty_result"],
            notable_facts=["查询没有返回记录。"],
            limitations=["空结果可能表示筛选条件过窄，或源数据中没有匹配记录。"],
        )

    profiles = {column: _profile_column(column, [row.get(column) for row in rows]) for column in columns}
    patterns = _detect_patterns(profiles, row_count, query_plan or {})
    notable_facts = _notable_facts(profiles, patterns, row_count)
    anomalies = _detect_anomalies(profiles)
    limitations = _limitations(row_count, rows)

    return ResultProfile(
        row_count=row_count,
        column_profiles=profiles,
        detected_patterns=patterns,
        notable_facts=notable_facts,
        anomalies=anomalies,
        limitations=limitations,
    )


def _profile_column(column: str, values: list[Any]) -> ColumnProfile:
    non_null = [value for value in values if value not in (None, "")]
    sample_values = _unique_preview(non_null)
    distinct_count = len({str(value) for value in non_null})

    numeric_values = [_coerce_number(value) for value in non_null]
    numeric_values = [value for value in numeric_values if value is not None]
    if non_null and len(numeric_values) >= max(1, int(len(non_null) * 0.8)):
        total = sum(numeric_values)  # type: ignore[arg-type]
        return ColumnProfile(
            kind="numeric",
            count=len(values),
            null_count=len(values) - len(non_null),
            distinct_count=distinct_count,
            sample_values=sample_values,
            min=round(min(numeric_values), 4),  # type: ignore[arg-type,type-var]
            max=round(max(numeric_values), 4),  # type: ignore[arg-type,type-var]
            sum=round(total, 4),
            avg=round(total / len(numeric_values), 4),
        )

    time_values = [_coerce_time(value) for value in non_null]
    time_values = [value for value in time_values if value is not None]
    if non_null and len(time_values) >= max(1, int(len(non_null) * 0.8)):
        return ColumnProfile(
            kind="time",
            count=len(values),
            null_count=len(values) - len(non_null),
            distinct_count=distinct_count,
            sample_values=sample_values,
            min=min(time_values).isoformat(),  # type: ignore[union-attr,type-var]
            max=max(time_values).isoformat(),  # type: ignore[union-attr,type-var]
        )

    top_values = [
        {"value": value, "count": count}
        for value, count in Counter(str(value) for value in non_null).most_common(5)
    ]
    return ColumnProfile(
        kind="category" if non_null else "unknown",
        count=len(values),
        null_count=len(values) - len(non_null),
        distinct_count=distinct_count,
        sample_values=sample_values,
        top_values=top_values,
    )


def _detect_patterns(
    profiles: dict[str, ColumnProfile],
    row_count: int,
    query_plan: dict[str, Any],
) -> list[str]:
    numeric_cols = [name for name, profile in profiles.items() if profile.kind == "numeric"]
    category_cols = [name for name, profile in profiles.items() if profile.kind == "category"]
    time_cols = [name for name, profile in profiles.items() if profile.kind == "time" or _looks_temporal(name)]
    patterns: list[str] = []

    if row_count == 1 and len(numeric_cols) == 1:
        patterns.append("single_metric")
    if time_cols and numeric_cols:
        patterns.append("time_series")
    if category_cols and numeric_cols:
        patterns.append("category_breakdown")
    if row_count <= 20 and category_cols and numeric_cols:
        patterns.append("top_k")
    if query_plan.get("time_range"):
        patterns.append("time_filtered")
    if not patterns:
        patterns.append("table_sample")
    return patterns


def _notable_facts(
    profiles: dict[str, ColumnProfile],
    patterns: list[str],
    row_count: int,
) -> list[str]:
    facts = [f"结果包含 {row_count} 行可分析记录。"]
    numeric_profiles = [(name, profile) for name, profile in profiles.items() if profile.kind == "numeric"]
    category_profiles = [(name, profile) for name, profile in profiles.items() if profile.kind == "category"]

    if "single_metric" in patterns and numeric_profiles:
        name, profile = numeric_profiles[0]
        facts.append(f"{name} 为 {profile.max}。")
    if category_profiles:
        name, profile = category_profiles[0]
        if profile.top_values:
            top = profile.top_values[0]
            facts.append(f"{name} 中最常见的值是 {top['value']}（{top['count']} 行）。")
    if numeric_profiles:
        name, profile = numeric_profiles[0]
        facts.append(f"{name} 的范围是 {_format_number(profile.min)} 到 {_format_number(profile.max)}。")
    return facts[:5]


def _detect_anomalies(profiles: dict[str, ColumnProfile]) -> list[str]:
    anomalies: list[str] = []
    for name, profile in profiles.items():
        if profile.kind != "numeric" or profile.avg in (None, 0) or profile.max is None:
            continue
        try:
            max_value = float(profile.max)
            avg_value = float(profile.avg)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if max_value >= avg_value * 3 and max_value > 0:
            anomalies.append(f"{name} 的最大值相对平均值偏高。")
    return anomalies


def _limitations(row_count: int, rows: list[dict[str, Any]]) -> list[str]:
    limitations = ["结果画像基于本次返回给 Agent 的行，不一定代表完整源表。"]
    if row_count >= 100 or len(rows) >= 100:
        limitations.append("结果可能经过抽样或截断；如需总量，请使用更聚焦的聚合查询核验。")
    return limitations


def _format_number(value: float | str | None) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _unique_preview(values: list[Any], limit: int = 5) -> list[Any]:
    seen: set[str] = set()
    preview: list[Any] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        preview.append(value)
        if len(preview) >= limit:
            break
    return preview


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def _coerce_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _looks_temporal(column: str) -> bool:
    lowered = column.lower()
    return any(token in lowered for token in ("date", "time", "day", "month", "year", "created_at", "updated_at"))
