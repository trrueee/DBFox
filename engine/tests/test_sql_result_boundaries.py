from __future__ import annotations

import json

import pytest

from engine.sql.guardrail import guardrail_check
from engine.sql.row_serializer import (
    JSON_OVERHEAD_BYTES,
    MAX_COLUMNS,
    MAX_ROWS,
    QueryExecutionResult,
    ResultTruncation,
    _fetch_and_serialize,
    _process_rows,
)


class _Cursor:
    def __init__(self, rows: list[dict[str, object]], columns: list[str]) -> None:
        self._rows = rows
        self.description = [(column,) for column in columns]
        self.fetchmany_sizes: list[int] = []

    def fetchmany(self, size: int) -> list[dict[str, object]]:
        self.fetchmany_sizes.append(size)
        return self._rows[:size]


def test_guardrail_clamps_explicit_limit_to_server_hard_cap() -> None:
    result = guardrail_check(f"SELECT id FROM users LIMIT {MAX_ROWS + 1}")

    assert result["result"] == "warn"
    assert result["safeSql"].upper().endswith(f"LIMIT {MAX_ROWS}")
    assert any(check["rule"] == "limit_hard_cap" for check in result["checks"])


def test_guardrail_adds_outer_hard_cap_when_only_nested_limit_exists() -> None:
    result = guardrail_check(
        f"SELECT * FROM (SELECT id FROM users LIMIT {MAX_ROWS + 1}) AS source"
    )

    assert result["result"] == "warn"
    assert result["safeSql"].upper().endswith(f"LIMIT {MAX_ROWS}")
    assert any(check["rule"] == "auto_limit" for check in result["checks"])


def test_guardrail_rewrites_fetch_with_ties_to_a_strict_hard_cap() -> None:
    result = guardrail_check(
        f"SELECT id FROM users FETCH FIRST {MAX_ROWS} ROWS WITH TIES",
        dialect="postgres",
    )

    assert result["result"] == "warn"
    assert result["safeSql"].upper().endswith(f"LIMIT {MAX_ROWS}")
    assert any(check["rule"] == "limit_hard_cap" for check in result["checks"])


def test_server_hard_cap_is_an_informational_agent_readonly_warning(
    db_session,
    test_datasource,
) -> None:
    from engine.schema_sync import sync_schema
    from engine.sql.safety_gate import validate_sql_schema
    from engine.sql.trust_gate import TrustGate

    sync_schema(db_session, test_datasource.id)
    decision = TrustGate(db_session, validate_sql_schema).execution_decision(
        test_datasource.id,
        f"SELECT id FROM users LIMIT {MAX_ROWS + 1}",
        policy="agent_readonly",
    )

    assert decision.can_execute is True
    assert decision.passed is True
    assert decision.requires_confirmation is False
    assert decision.safe_sql.endswith(f"LIMIT {MAX_ROWS}")


@pytest.mark.parametrize(
    ("source_row_count", "expected_row_truncated"),
    [
        (MAX_ROWS, False),
        (MAX_ROWS + 1, True),
    ],
)
def test_fetch_uses_extra_row_to_mark_row_limit_truncation(
    source_row_count: int,
    expected_row_truncated: bool,
) -> None:
    rows = [{"id": index} for index in range(source_row_count)]
    cursor = _Cursor(rows, ["id"])

    result = _fetch_and_serialize(cursor)

    assert cursor.fetchmany_sizes == [MAX_ROWS + 1]
    assert len(result.rows) == min(source_row_count, MAX_ROWS)
    assert result.truncation.rows is expected_row_truncated
    assert result.truncated is expected_row_truncated


@pytest.mark.parametrize(
    ("column_count", "expected_columns_truncated"),
    [
        (MAX_COLUMNS, False),
        (MAX_COLUMNS + 1, True),
    ],
)
def test_column_limit_has_its_own_truncation_marker(
    column_count: int,
    expected_columns_truncated: bool,
) -> None:
    columns = [f"column_{index}" for index in range(column_count)]
    result = _process_rows([{column: column for column in columns}], columns)

    assert len(result.columns) == min(column_count, MAX_COLUMNS)
    assert result.truncation.columns is expected_columns_truncated
    assert result.truncated is expected_columns_truncated


def test_response_byte_boundary_is_exact_and_independent() -> None:
    raw_row = {"value": "x"}
    serialized_row_bytes = len(
        json.dumps(raw_row, ensure_ascii=False, default=str).encode("utf-8")
    )
    one_row_payload_bytes = JSON_OVERHEAD_BYTES + serialized_row_bytes

    exact = _process_rows(
        [raw_row],
        ["value"],
        max_response_bytes=one_row_payload_bytes,
    )
    overflow = _process_rows(
        [raw_row, raw_row],
        ["value"],
        max_response_bytes=one_row_payload_bytes,
    )

    assert exact.rows == [raw_row]
    assert exact.response_bytes == one_row_payload_bytes
    assert exact.truncation == ResultTruncation()
    assert exact.truncated is False

    assert overflow.rows == [raw_row]
    assert overflow.response_bytes == one_row_payload_bytes
    assert overflow.truncation.response_bytes is True
    assert overflow.truncated is True


def test_response_bytes_match_the_complete_json_array_encoding() -> None:
    raw_rows = [{"value": "x"}, {"value": "y"}]
    expected_bytes = len(
        json.dumps(raw_rows, ensure_ascii=False, default=str).encode("utf-8")
    )

    result = _process_rows(
        raw_rows,
        ["value"],
        max_response_bytes=expected_bytes,
    )

    assert result.rows == raw_rows
    assert result.response_bytes == expected_bytes
    assert result.truncated is False


def test_executor_exposes_independent_truncation_reasons(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    import engine.sql.executor as executor
    from engine.schema_sync import sync_schema

    sync_schema(db_session, test_datasource.id)
    bounded_result = QueryExecutionResult(
        rows=[{"id": "1"}],
        columns=["id"],
        truncation=ResultTruncation(
            rows=True,
            columns=True,
            response_bytes=True,
            cells=True,
        ),
        response_bytes=32,
        connect_ms=0,
        execute_ms=0,
        fetch_ms=0,
        serialize_ms=0,
    )
    monkeypatch.setattr(executor, "_execute_on_sqlite_profiled", lambda *_args, **_kwargs: bounded_result)

    result = executor.execute_query(
        db_session,
        test_datasource.id,
        "SELECT id FROM users LIMIT 1",
        redact=False,
    )

    assert result["truncated"] is True
    assert result["rowTruncated"] is True
    assert result["columnTruncated"] is True
    assert result["responseBytesTruncated"] is True
    assert result["cellTruncated"] is True
    assert any("1000" in warning for warning in result["warnings"])
    assert any("100" in warning for warning in result["warnings"])
    assert any("字节" in warning for warning in result["warnings"])


def test_executor_recalculates_response_bytes_after_redaction(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    import engine.policy.sensitivity as sensitivity_module
    import engine.sql.executor as executor
    from engine.schema_sync import sync_schema

    sync_schema(db_session, test_datasource.id)
    bounded_result = QueryExecutionResult(
        rows=[{"id": "1"}],
        columns=["id"],
        truncation=ResultTruncation(),
        response_bytes=JSON_OVERHEAD_BYTES + len(b'{"id": "1"}'),
        connect_ms=0,
        execute_ms=0,
        fetch_ms=0,
        serialize_ms=0,
    )
    monkeypatch.setattr(executor, "_execute_on_sqlite_profiled", lambda *_args, **_kwargs: bounded_result)
    monkeypatch.setattr(sensitivity_module, "load_sensitivity", lambda *_args: None)
    monkeypatch.setattr(
        sensitivity_module,
        "redact_row",
        lambda _row, _sensitivity: {"id": "[REDACTED-LONGER-THAN-ONE]"},
    )

    result = executor.execute_query(
        db_session,
        test_datasource.id,
        "SELECT id FROM users LIMIT 1",
    )
    expected_bytes = JSON_OVERHEAD_BYTES + len(
        json.dumps(result["rows"][0], ensure_ascii=False, default=str).encode("utf-8")
    )

    assert result["responseBytes"] == expected_bytes
    assert result["responseBytes"] > bounded_result.response_bytes
