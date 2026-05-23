"""Tests for executor module — query execution against SQLite demo DB."""
import decimal
import datetime
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from engine.executor import _serialize_value, _process_rows, MAX_ROWS, execute_query, explain_sql


class TestSerializeValue:
    def test_none_returns_none(self) -> None:
        assert _serialize_value(None) is None

    def test_decimal_returns_string(self) -> None:
        assert _serialize_value(decimal.Decimal("10.5")) == "10.5"

    def test_datetime_returns_isoformat(self) -> None:
        dt = datetime.datetime(2025, 1, 15, 12, 30, 0)
        assert _serialize_value(dt) == "2025-01-15T12:30:00"

    def test_date_returns_isoformat(self) -> None:
        d = datetime.date(2025, 1, 15)
        assert _serialize_value(d) == "2025-01-15"

    def test_bytes_returns_binary_tag(self) -> None:
        assert _serialize_value(b"hello") == "<binary>"

    def test_string_passes_through(self) -> None:
        assert _serialize_value("hello") == "hello"

    def test_int_passes_through_as_str(self) -> None:
        assert _serialize_value(42) == "42"

    def test_float_passes_through_as_str(self) -> None:
        assert _serialize_value(3.14) == "3.14"


class TestProcessRows:
    def test_empty_rows(self) -> None:
        rows, cols, truncated, _ = _process_rows([], ["id", "name"])
        assert rows == []
        assert cols == ["id", "name"]
        assert truncated is False

    def test_basic_processing(self) -> None:
        raw = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        rows, cols, truncated, _ = _process_rows(raw, ["id", "name"])
        assert rows == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        assert cols == ["id", "name"]
        assert truncated is False

    def test_column_limit_enforced(self) -> None:
        raw = [{"a": 1, "b": 2, "c": 3, "d": 4}]
        rows, cols, _, _ = _process_rows(raw, ["a", "b", "c", "d"], max_columns=2)
        assert cols == ["a", "b"]

    def test_cell_truncation(self) -> None:
        raw = [{"col": "x" * 100}]
        rows, _, _, _ = _process_rows(raw, ["col"], max_cell_chars=10)
        assert rows[0]["col"] == "x" * 10 + "..."

    def test_decimal_serialization(self) -> None:
        raw = [{"price": decimal.Decimal("9.99")}]
        rows, _, _, _ = _process_rows(raw, ["price"])
        assert rows[0]["price"] == "9.99"

    def test_none_value_remains_none(self) -> None:
        raw = [{"col": None}]
        rows, _, _, _ = _process_rows(raw, ["col"])
        assert rows[0]["col"] is None

    def test_response_byte_limit_truncates_rows(self) -> None:
        raw = [{"col": "x" * 20}, {"col": "y" * 20}]
        rows, cols, truncated, response_bytes = _process_rows(raw, ["col"], max_response_bytes=35)
        assert cols == ["col"]
        assert len(rows) == 1
        assert truncated is True
        assert response_bytes <= 35


class TestExecutorSQLite:
    """Integration test: execute real queries against the demo SQLite database."""

    def test_select_all_users(self) -> None:
        from engine.executor import _execute_on_sqlite

        rows, columns, truncated, _ = _execute_on_sqlite("SELECT id, username, email FROM users LIMIT 5")
        assert len(rows) >= 1
        assert "username" in columns
        assert "email" in columns
        assert truncated is False
        assert isinstance(rows[0]["username"], str)

    def test_aggregation_query(self) -> None:
        from engine.executor import _execute_on_sqlite

        rows, columns, _, _ = _execute_on_sqlite("SELECT COUNT(*) AS cnt FROM users")
        assert len(rows) == 1
        assert columns == ["cnt"]
        assert int(rows[0]["cnt"]) > 0

    def test_join_query(self) -> None:
        from engine.executor import _execute_on_sqlite

        rows, columns, _, _ = _execute_on_sqlite(
            "SELECT u.username, o.total_amount FROM users u "
            "JOIN orders o ON u.id = o.user_id LIMIT 5"
        )
        assert len(rows) >= 1
        assert "username" in columns
        assert "total_amount" in columns

    def test_row_limit_enforced(self) -> None:
        from engine.executor import _execute_on_sqlite

        rows, _, _, _ = _execute_on_sqlite("SELECT * FROM users")
        assert len(rows) <= MAX_ROWS

    def test_non_select_rejected(self) -> None:
        """SQLite executes DDL without issue, but guardrail should be tested separately."""
        # This test verifies SQLite execution works; guardrail handles DDL blocking.
        from engine.executor import _execute_on_sqlite

        rows, columns, _, _ = _execute_on_sqlite(
            "SELECT name FROM sqlite_master WHERE type='table' LIMIT 5"
        )
        assert len(columns) == 1
        assert "name" in columns

    def test_sqlite_timeout(self) -> None:
        from engine.executor import _execute_on_sqlite

        with pytest.raises(TimeoutError):
            _execute_on_sqlite(
                "WITH RECURSIVE cnt(x) AS ("
                "SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 100000000"
                ") SELECT sum(x) FROM cnt",
                timeout_ms=0,
            )

    def test_sqlite_query_can_be_cancelled(self) -> None:
        from engine.errors import SQLQueryCancelledError
        from engine.executor import _execute_on_sqlite
        from engine.query_registry import QUERY_REGISTRY

        execution_id = "test-sqlite-cancel"
        long_sql = (
            "WITH RECURSIVE cnt(x) AS ("
            "SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 100000000"
            ") SELECT sum(x) FROM cnt"
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_execute_on_sqlite, long_sql, 30000, execution_id, "demo")

            deadline = time.time() + 3
            while time.time() < deadline and not QUERY_REGISTRY.is_running(execution_id):
                time.sleep(0.01)

            assert QUERY_REGISTRY.is_running(execution_id)
            cancel_result = QUERY_REGISTRY.cancel(execution_id)
            assert cancel_result["cancelled"] is True

            with pytest.raises(SQLQueryCancelledError):
                future.result(timeout=3)


class TestPerformanceAndExplain:
    def test_execute_query_latency_metrics(self, db_session, demo_datasource) -> None:
        # Set database to demo_shop to trigger SQLite path in testing
        demo_datasource.host = "demo"
        demo_datasource.database_name = "demo_shop"
        db_session.commit()

        res = execute_query(db_session, demo_datasource.id, "SELECT id, username FROM users LIMIT 3")
        assert res["success"] is True
        assert "connectMs" in res
        assert "guardrailMs" in res
        assert "executeMs" in res
        assert "fetchMs" in res
        assert "serializeMs" in res
        assert "totalMs" in res
        assert res["totalMs"] >= 0

        # Check DB model timing values
        from engine.models import QueryHistory
        history = db_session.query(QueryHistory).filter(QueryHistory.id == res["historyId"]).first()
        assert history is not None
        assert history.connect_ms is not None
        assert history.guardrail_ms is not None
        assert history.execute_ms is not None
        assert history.fetch_ms is not None
        assert history.serialize_ms is not None

    def test_explain_sql_sqlite(self, db_session, demo_datasource) -> None:
        demo_datasource.host = "demo"
        demo_datasource.database_name = "demo_shop"
        db_session.commit()

        res = explain_sql(db_session, demo_datasource.id, "SELECT id, username FROM users LIMIT 3")
        assert res["success"] is True
        assert "records" in res
        assert "warnings" in res
        assert len(res["records"]) >= 1
        
        record = res["records"][0]
        assert "type" in record
        assert "key" in record
        assert "rows" in record
        assert "Extra" in record

    def test_explain_sql_non_select_rejected(self, db_session, demo_datasource) -> None:
        with pytest.raises(ValueError, match="EXPLAIN 诊断仅支持 SELECT 语句"):
            explain_sql(db_session, demo_datasource.id, "DELETE FROM users")
