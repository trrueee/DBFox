from __future__ import annotations

import datetime
import decimal
import time
from dataclasses import dataclass, replace
from typing import Any

from engine.json_codec import byte_size
from engine.sql.result_limits import (
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_RESPONSE_BYTES,
    MAX_ROWS,
)

JSON_OVERHEAD_BYTES = 2  # Represents the brackets '[' and ']' of the JSON array wrapper
JSON_ARRAY_ITEM_SEPARATOR_BYTES = 1
TRUNCATION_SUFFIX = "..."
TRUNCATION_LEN = len(TRUNCATION_SUFFIX)


@dataclass(frozen=True)
class ResultTruncation:
    """Independent reasons why a tabular result was shortened for transport."""

    rows: bool = False
    columns: bool = False
    response_bytes: bool = False
    cells: bool = False

    @property
    def truncated(self) -> bool:
        return self.rows or self.columns or self.response_bytes or self.cells

    def merged_with(self, other: "ResultTruncation") -> "ResultTruncation":
        """Combine independent limits applied at successive read-only stages."""
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
    """Common fetch/serialize logic shared by all database dialects.

    Args:
        row_mapper: Optional callable to convert each raw row to a dict.
                    Used by psycopg2 which returns tuples instead of dicts.

    Fetches one extra row to distinguish an exact row-limit result from a
    server result that had to be shortened.  The returned truncation reasons
    remain independent so callers can present an accurate result contract.
    """
    if max_rows < 0:
        raise ValueError("max_rows must be non-negative")

    if cursor.description:
        columns = [col[0] for col in cursor.description]

        t_fetch_start = time.perf_counter()
        raw_rows = list(cursor.fetchmany(max_rows + 1))
        row_limit_exceeded = len(raw_rows) > max_rows
        raw_rows = raw_rows[:max_rows]
        if row_mapper:
            raw_rows = [row_mapper(r) for r in raw_rows]
        fetch_ms = int((time.perf_counter() - t_fetch_start) * 1000)

        t_ser_start = time.perf_counter()
        processed = _process_rows(raw_rows, columns)
        if row_limit_exceeded:
            processed = SerializedRows(
                rows=processed.rows,
                columns=processed.columns,
                truncation=replace(processed.truncation, rows=True),
                response_bytes=processed.response_bytes,
            )
        serialize_ms = int((time.perf_counter() - t_ser_start) * 1000)
        return FetchSerializationResult(
            rows=processed.rows,
            columns=processed.columns,
            truncation=processed.truncation,
            response_bytes=processed.response_bytes,
            fetch_ms=fetch_ms,
            serialize_ms=serialize_ms,
        )

    return FetchSerializationResult(
        rows=[],
        columns=[],
        truncation=ResultTruncation(),
        response_bytes=JSON_OVERHEAD_BYTES,
        fetch_ms=0,
        serialize_ms=0,
    )


def _serialize_value(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, decimal.Decimal):
        return str(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return "<binary>"
    return str(val)


def serialize_rows(
    raw_rows: list[Any],
    columns: list[str],
    max_columns: int = MAX_COLUMNS,
    max_cell_chars: int = MAX_CELL_CHARS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> SerializedRows:
    """Serialize rows while enforcing independently-reportable transport limits.

    This is the shared public boundary for database responses and bounded Agent
    observations.  Callers choose their own smaller limits; no caller should
    truncate an already-rendered JSON string.
    """
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
    response_bytes = JSON_OVERHEAD_BYTES  # JSON array brackets
    truncation = ResultTruncation(columns=len(original_columns) > len(columns))

    for r in raw_rows:
        row_dict: dict[str, Any] = {}
        for col in columns:
            val = r[col]
            if isinstance(val, str) and len(val) > max_cell_chars:
                val = val[:max_cell_chars] + TRUNCATION_SUFFIX
                truncation = replace(truncation, cells=True)
            row_dict[col] = _serialize_value(val)

        row_bytes = byte_size(row_dict)
        # Compact JSON arrays contribute one comma between rows.
        separator_bytes = JSON_ARRAY_ITEM_SEPARATOR_BYTES if rows else 0
        if response_bytes + separator_bytes + row_bytes > max_response_bytes:
            truncation = replace(truncation, response_bytes=True)
            break

        response_bytes += separator_bytes + row_bytes
        rows.append(row_dict)

    return SerializedRows(
        rows=rows,
        columns=columns,
        truncation=truncation,
        response_bytes=response_bytes,
    )


# Kept private inside this module so existing database-driver paths remain
# readable while all external callers use the public, tested contract above.
_process_rows = serialize_rows
