from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.app.safe_errors import FixedErrorCode, fixed_error_message


@dataclass
class SqlExecutionResult:
    success: bool
    rows: list[tuple[Any, ...]]
    error: str | None = None


@dataclass
class SqlComparisonResult:
    gold_success: bool
    predicted_success: bool
    execution_match: bool
    gold_error: str | None = None
    predicted_error: str | None = None
    gold_rows_count: int = 0
    predicted_rows_count: int = 0


def execute_sqlite_query(db_path: str | Path, sql: str, *, timeout_seconds: int = 10) -> SqlExecutionResult:
    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout_seconds)
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            return SqlExecutionResult(success=True, rows=[tuple(row) for row in rows])
        finally:
            conn.close()
    except Exception:
        return SqlExecutionResult(
            success=False,
            rows=[],
            error=fixed_error_message(FixedErrorCode.SQL_EXECUTION_FAILED),
        )


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return round(value, 6)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    try:
        number = float(text)
        return round(number, 6)
    except ValueError:
        return text.lower()


def normalize_rows(rows: list[tuple[Any, ...]], *, order_sensitive: bool = False) -> list[tuple[Any, ...]]:
    normalized = [tuple(normalize_value(v) for v in row) for row in rows]
    if order_sensitive:
        return normalized
    try:
        return sorted(normalized, key=lambda t: tuple(str(x) for x in t))
    except TypeError:
        return sorted(normalized, key=repr)


def is_order_sensitive(sql: str) -> bool:
    return "order by" in sql.lower()


def compare_sqlite_execution(db_path: str | Path, gold_sql: str, predicted_sql: str) -> SqlComparisonResult:
    gold = execute_sqlite_query(db_path, gold_sql)
    predicted = execute_sqlite_query(db_path, predicted_sql)

    if not gold.success or not predicted.success:
        return SqlComparisonResult(
            gold_success=gold.success,
            predicted_success=predicted.success,
            execution_match=False,
            gold_error=gold.error,
            predicted_error=predicted.error,
            gold_rows_count=len(gold.rows),
            predicted_rows_count=len(predicted.rows),
        )

    order_sensitive = is_order_sensitive(gold_sql) or is_order_sensitive(predicted_sql)
    match = normalize_rows(gold.rows, order_sensitive=order_sensitive) == normalize_rows(
        predicted.rows, order_sensitive=order_sensitive,
    )

    return SqlComparisonResult(
        gold_success=True,
        predicted_success=True,
        execution_match=match,
        gold_rows_count=len(gold.rows),
        predicted_rows_count=len(predicted.rows),
    )
