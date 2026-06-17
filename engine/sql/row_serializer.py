from __future__ import annotations

import datetime
import decimal
import json
import time
from typing import Any

MAX_ROWS = 1000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 5000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_MS = 30_000

ProcessedRows = tuple[list[dict[str, Any]], list[str], bool, int]


def _fetch_and_serialize(cursor: Any, max_rows: int = MAX_ROWS, *, row_mapper: Any = None) -> tuple[list[dict[str, Any]], list[str], bool, int, int, int]:
    """Common fetch/serialize logic shared by all database dialects.

    Args:
        row_mapper: Optional callable to convert each raw row to a dict.
                    Used by psycopg2 which returns tuples instead of dicts.

    Returns (rows, columns, truncated, response_bytes, fetch_ms, serialize_ms).
    """
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    truncated = False
    response_bytes = 2
    fetch_ms = 0
    serialize_ms = 0

    if cursor.description:
        columns = [col[0] for col in cursor.description]

        t_fetch_start = time.perf_counter()
        raw_rows = cursor.fetchmany(max_rows)
        if row_mapper:
            raw_rows = [row_mapper(r) for r in raw_rows]
        fetch_ms = int((time.perf_counter() - t_fetch_start) * 1000)

        t_ser_start = time.perf_counter()
        rows, columns, truncated, response_bytes = _process_rows(raw_rows, columns)
        serialize_ms = int((time.perf_counter() - t_ser_start) * 1000)

    return rows, columns, truncated, response_bytes, fetch_ms, serialize_ms


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


def _process_rows(
    raw_rows: list[Any],
    columns: list[str],
    max_columns: int = MAX_COLUMNS,
    max_cell_chars: int = MAX_CELL_CHARS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> ProcessedRows:
    """Process raw cursor rows into a list of serialized dicts with limits applied."""
    if len(columns) > max_columns:
        columns = columns[:max_columns]

    rows = []
    response_bytes = 2  # JSON array brackets
    truncated = False

    for r in raw_rows:
        row_dict = {}
        for col in columns:
            val = r[col]
            if isinstance(val, str) and len(val) > max_cell_chars:
                val = val[:max_cell_chars] + "..."
            row_dict[col] = _serialize_value(val)

        row_bytes = len(json.dumps(row_dict, ensure_ascii=False, default=str).encode("utf-8")) + 1
        if response_bytes + row_bytes > max_response_bytes:
            truncated = True
            break

        response_bytes += row_bytes
        rows.append(row_dict)

    return rows, columns, truncated, response_bytes
