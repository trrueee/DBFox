"""Pure, deterministic analysis of bounded Data result rows."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from statistics import fmean, median
from typing import Any

MAX_PROFILE_VALUE_CHARS = 256


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(Decimal(str(value).strip().replace(",", "")))
    except (InvalidOperation, ValueError):
        return None
    return number if isfinite(number) else None


def _temporal(value: object) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) < 8:
        return None
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00")).isoformat()
    except ValueError:
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            return None


def profile_rows(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    return [
        _profile_column(column, [row.get(column) for row in rows], top_k=top_k)
        for column in columns
    ]


def _profile_column(
    column: str,
    values: list[object],
    *,
    top_k: int,
) -> dict[str, Any]:
    present = [value for value in values if value is not None]
    numeric = [_number(value) for value in present]
    temporal = [_temporal(value) for value in present]
    if not present:
        kind = "empty"
    elif all(value is not None for value in numeric):
        kind = "number"
    elif all(isinstance(value, bool) for value in present):
        kind = "boolean"
    elif all(value is not None for value in temporal):
        kind = "datetime"
    elif all(isinstance(value, str) for value in present):
        kind = "string"
    else:
        kind = "mixed"
    encoded = [_profile_value(value) for value in present]
    profile: dict[str, Any] = {
        "column": column,
        "kind": kind,
        "sample_count": len(values),
        "non_null_count": len(present),
        "null_count": len(values) - len(present),
        "distinct_count": len({value[0] for value in encoded}),
    }
    if kind == "number":
        numbers = [value for value in numeric if value is not None]
        profile["numeric"] = {
            "min": min(numbers),
            "max": max(numbers),
            "mean": fmean(numbers),
            "median": median(numbers),
        }
    elif kind == "datetime":
        timestamps = [value for value in temporal if value is not None]
        profile["temporal"] = {"min": min(timestamps), "max": max(timestamps)}
    counts = Counter(key for key, _ in encoded)
    display = {key: value for key, value in encoded}
    profile["top_values"] = [
        {"value": display[key], "count": count, "share": count / len(present)}
        for key, count in counts.most_common(top_k)
    ]
    return profile


def _profile_value(value: object) -> tuple[str, str | int | float | bool]:
    number = _number(value)
    if number is not None:
        return f"number:{number}", number
    if isinstance(value, bool):
        return f"boolean:{value}", value
    temporal = _temporal(value)
    if temporal is not None:
        return f"datetime:{temporal}", temporal
    text = str(value)
    display = text if len(text) <= MAX_PROFILE_VALUE_CHARS else f"{text[:MAX_PROFILE_VALUE_CHARS - 1]}…"
    return f"value:{text}", display
