"""Bounded, JSON-safe serialization for database result rows."""

from __future__ import annotations

import datetime
import decimal
import json
import time
from dataclasses import dataclass, replace
from typing import Any

from .result_limits import MAX_CELL_CHARS, MAX_COLUMNS, MAX_RESPONSE_BYTES, MAX_ROWS

JSON_OVERHEAD_BYTES = 2
JSON_ARRAY_ITEM_SEPARATOR_BYTES = 1
TRUNCATION_SUFFIX = "..."


@dataclass(frozen=True)
class ResultTruncation:
    rows: bool = False
    columns: bool = False
    response_bytes: bool = False
    cells: bool = False

    @property
    def truncated(self) -> bool:
        return self.rows or self.columns or self.response_bytes or self.cells

    def merged_with(self, other: "ResultTruncation") -> "ResultTruncation":
        return ResultTruncation(
            rows=self.rows or other.rows,
            columns=self.columns or other.columns,
            response_bytes=self.response_bytes or other.response_bytes,
            cells=self.cells or other.cells,
        )


@dataclass(frozen=True)
class SerializedRows:
    rows: list[dict[str, Any]]
    columns: list[str]
    truncation: ResultTruncation
    response_bytes: int

    @property
    def truncated(self) -> bool:
        return self.truncation.truncated


@dataclass(frozen=True)
class FetchSerializationResult(SerializedRows):
    fetch_ms: int
    serialize_ms: int


@dataclass(frozen=True)
class QueryExecutionResult(SerializedRows):
    connect_ms: int
    execute_ms: int
    fetch_ms: int
    serialize_ms: int

    @classmethod
    def from_fetch_result(
        cls,
        result: FetchSerializationResult,
        *,
        connect_ms: int,
        execute_ms: int,
    ) -> "QueryExecutionResult":
        return cls(
            rows=result.rows,
            columns=result.columns,
            truncation=result.truncation,
            response_bytes=result.response_bytes,
            connect_ms=connect_ms,
            execute_ms=execute_ms,
            fetch_ms=result.fetch_ms,
            serialize_ms=result.serialize_ms,
        )


def _fetch_and_serialize(
    cursor: Any,
    max_rows: int = MAX_ROWS,
    *,
    row_mapper: Any = None,
) -> FetchSerializationResult:
    if max_rows < 0:
        raise ValueError("max_rows must be non-negative")
    if not cursor.description:
        return FetchSerializationResult(
            rows=[],
            columns=[],
            truncation=ResultTruncation(),
            response_bytes=JSON_OVERHEAD_BYTES,
            fetch_ms=0,
            serialize_ms=0,
        )

    columns = [str(column[0]) for column in cursor.description]
    fetch_started = time.perf_counter()
    raw_rows = list(cursor.fetchmany(max_rows + 1))
    row_limit_exceeded = len(raw_rows) > max_rows
    raw_rows = raw_rows[:max_rows]
    if row_mapper:
        raw_rows = [row_mapper(row) for row in raw_rows]
    fetch_ms = int((time.perf_counter() - fetch_started) * 1_000)

    serialization_started = time.perf_counter()
    processed = serialize_rows(raw_rows, columns)
    if row_limit_exceeded:
        processed = SerializedRows(
            rows=processed.rows,
            columns=processed.columns,
            truncation=replace(processed.truncation, rows=True),
            response_bytes=processed.response_bytes,
        )
    return FetchSerializationResult(
        rows=processed.rows,
        columns=processed.columns,
        truncation=processed.truncation,
        response_bytes=processed.response_bytes,
        fetch_ms=fetch_ms,
        serialize_ms=int((time.perf_counter() - serialization_started) * 1_000),
    )


def _serialize_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "<binary>"
    return str(value)


def _byte_size(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def serialize_rows(
    raw_rows: list[Any],
    columns: list[str],
    max_columns: int = MAX_COLUMNS,
    max_cell_chars: int = MAX_CELL_CHARS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> SerializedRows:
    if max_columns < 0:
        raise ValueError("max_columns must be non-negative")
    if max_cell_chars < 0:
        raise ValueError("max_cell_chars must be non-negative")
    if max_response_bytes < JSON_OVERHEAD_BYTES:
        raise ValueError(
            f"max_response_bytes must be at least {JSON_OVERHEAD_BYTES} for a JSON array"
        )

    original_columns = columns
    columns = original_columns[:max_columns]
    rows: list[dict[str, Any]] = []
    response_bytes = JSON_OVERHEAD_BYTES
    truncation = ResultTruncation(columns=len(original_columns) > len(columns))

    for raw_row in raw_rows:
        row: dict[str, Any] = {}
        for column in columns:
            serialized = _serialize_value(raw_row[column])
            if isinstance(serialized, str) and len(serialized) > max_cell_chars:
                serialized = serialized[:max_cell_chars] + TRUNCATION_SUFFIX
                truncation = replace(truncation, cells=True)
            row[column] = serialized
        row_bytes = _byte_size(row)
        separator_bytes = JSON_ARRAY_ITEM_SEPARATOR_BYTES if rows else 0
        if response_bytes + separator_bytes + row_bytes > max_response_bytes:
            truncation = replace(truncation, response_bytes=True)
            break
        response_bytes += separator_bytes + row_bytes
        rows.append(row)

    return SerializedRows(
        rows=rows,
        columns=columns,
        truncation=truncation,
        response_bytes=response_bytes,
    )


_process_rows = serialize_rows
