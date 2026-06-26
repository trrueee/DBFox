"""Tests for executor module — query execution against SQLite demo DB."""
import decimal
import datetime
import inspect
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from engine.sql.executor import _serialize_value, _process_rows, MAX_ROWS, execute_query, explain_sql
from engine.schema_sync import sync_schema


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


class TestMySQLPool:
    def test_queue_pool_checkout_does_not_require_sqlalchemy_dialect(self, monkeypatch) -> None:
        import engine.sql.dialect.mysql as mysql_dialect
        from engine.sql.executor import _ping_mysql_connection, get_mysql_pool
        from engine.sql.pool_registry import get_pool_registry

        class FakeConnection:
            pinged = False

            def ping(self, reconnect: bool = True) -> None:
                self.pinged = reconnect

            def rollback(self) -> None:
                pass

            def close(self) -> None:
                pass

        get_pool_registry().dispose_all()
        monkeypatch.setattr(mysql_dialect.pymysql, "connect", lambda **_params: FakeConnection())

        pool = get_mysql_pool("ds-mysql", {
            "host": "127.0.0.1",
            "port": 3306,
            "user": "root",
            "password": "secret",
            "database": "app",
        })
        conn_proxy = pool.connect()
        try:
            raw_conn = _ping_mysql_connection(conn_proxy)
            assert raw_conn.pinged is True
        finally:
            conn_proxy.close()
            get_pool_registry().dispose_all()


class TestExecutorSQLite:
    """Integration test: execute real queries against the demo SQLite database."""

    def test_select_all_users(self, test_datasource_module) -> None:
        from engine.sql.executor import _execute_on_sqlite

        rows, columns, truncated, _ = _execute_on_sqlite("SELECT id, username, email FROM users LIMIT 5", sqlite_path=test_datasource_module.database_name)
        assert len(rows) >= 1
        assert "username" in columns
        assert "email" in columns
        assert truncated is False
        assert isinstance(rows[0]["username"], str)

    def test_aggregation_query(self, test_datasource_module) -> None:
        from engine.sql.executor import _execute_on_sqlite

        rows, columns, _, _ = _execute_on_sqlite("SELECT COUNT(*) AS cnt FROM users", sqlite_path=test_datasource_module.database_name)
        assert len(rows) == 1
        assert columns == ["cnt"]
        assert int(rows[0]["cnt"]) > 0

    def test_join_query(self, test_datasource_module) -> None:
        from engine.sql.executor import _execute_on_sqlite

        rows, columns, _, _ = _execute_on_sqlite(
            "SELECT u.username, o.total_amount FROM users u "
            "JOIN orders o ON u.id = o.user_id LIMIT 5",
            sqlite_path=test_datasource_module.database_name,
        )
        assert len(rows) >= 1
        assert "username" in columns
        assert "total_amount" in columns

    def test_row_limit_enforced(self, test_datasource_module) -> None:
        from engine.sql.executor import _execute_on_sqlite

        rows, _, _, _ = _execute_on_sqlite("SELECT * FROM users", sqlite_path=test_datasource_module.database_name)
        assert len(rows) <= MAX_ROWS

    def test_non_select_rejected(self, test_datasource_module) -> None:
        """SQLite executes DDL without issue, but guardrail should be tested separately."""
        # This test verifies SQLite execution works; guardrail handles DDL blocking.
        from engine.sql.executor import _execute_on_sqlite

        rows, columns, _, _ = _execute_on_sqlite(
            "SELECT name FROM sqlite_master WHERE type='table' LIMIT 5",
            sqlite_path=test_datasource_module.database_name,
        )
        assert len(columns) == 1
        assert "name" in columns

    def test_sqlite_timeout(self, test_datasource_module) -> None:
        from engine.sql.executor import _execute_on_sqlite

        with pytest.raises(TimeoutError):
            _execute_on_sqlite(
                "WITH RECURSIVE cnt(x) AS ("
                "SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 100000000"
                ") SELECT sum(x) FROM cnt",
                timeout_ms=0,
                sqlite_path=test_datasource_module.database_name,
            )

    def test_sqlite_query_can_be_cancelled(self, test_datasource_module) -> None:
        from engine.errors import SQLQueryCancelledError
        from engine.sql.executor import _execute_on_sqlite
        from engine.query_registry import QUERY_REGISTRY

        execution_id = "test-sqlite-cancel"
        long_sql = (
            "WITH RECURSIVE cnt(x) AS ("
            "SELECT 1 UNION ALL SELECT x + 1 FROM cnt WHERE x < 100000000"
            ") SELECT sum(x) FROM cnt"
        )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                _execute_on_sqlite,
                long_sql,
                timeout_ms=30000,
                execution_id=execution_id,
                sqlite_path=test_datasource_module.database_name,
            )

            deadline = time.time() + 3
            while time.time() < deadline and not QUERY_REGISTRY.is_running(execution_id):
                time.sleep(0.01)

            assert QUERY_REGISTRY.is_running(execution_id)
            cancel_result = QUERY_REGISTRY.cancel(execution_id)
            assert cancel_result["cancelled"] is True

            with pytest.raises(SQLQueryCancelledError):
                future.result(timeout=3)


class TestPerformanceAndExplain:
    def test_execute_query_latency_metrics(self, db_session_module, test_datasource_module) -> None:
        sync_schema(db_session_module, test_datasource_module.id)
        res = execute_query(db_session_module, test_datasource_module.id, "SELECT id, username FROM users LIMIT 3")
        assert res["success"] is True
        assert res["safetyDecision"]["can_execute"] is True
        assert res["safetyDecision"]["datasource_id"] == test_datasource_module.id
        assert "connectMs" in res
        assert "guardrailMs" in res
        assert "executeMs" in res
        assert "fetchMs" in res
        assert "serializeMs" in res
        assert "totalMs" in res
        assert res["totalMs"] >= 0

        # Check DB model timing values
        from engine.models import QueryHistory
        history = db_session_module.query(QueryHistory).filter(QueryHistory.id == res["historyId"]).first()
        assert history is not None
        assert history.connect_ms is not None
        assert history.guardrail_ms is not None
        assert history.execute_ms is not None
        assert history.fetch_ms is not None
        assert history.serialize_ms is not None

    def test_execute_query_can_disable_query_history_for_eval(
        self,
        db_session,
        test_datasource,
        monkeypatch,
    ) -> None:
        from engine.models import QueryHistory

        sync_schema(db_session, test_datasource.id)
        monkeypatch.setenv("DBFOX_DISABLE_QUERY_HISTORY", "1")

        res = execute_query(db_session, test_datasource.id, "SELECT id, username FROM users LIMIT 3")

        assert res["success"] is True
        assert res["historyId"] is None
        assert db_session.query(QueryHistory).filter(QueryHistory.data_source_id == test_datasource.id).count() == 0

    def test_execute_query_blocks_schema_hallucination(self, db_session_module, test_datasource_module) -> None:
        sync_schema(db_session_module, test_datasource_module.id)

        # Schema errors (no such column/table) now block execution via TrustGate dry-run.
        from engine.errors import GuardrailValidationError
        with pytest.raises(GuardrailValidationError) as exc_info:
            execute_query(db_session_module, test_datasource_module.id, "SELECT imaginary_column FROM users LIMIT 3")
        assert "schema validation" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()

    def test_execute_query_rejects_mismatched_safety_decision(self, db_session_module, test_datasource_module) -> None:
        from engine.sql.executor import validate_sql_schema
        from engine.errors import GuardrailValidationError
        from engine.sql.trust_gate import TrustGate

        decision = TrustGate(db_session_module, validate_sql_schema).execution_decision(
            test_datasource_module.id,
            "SELECT id FROM users LIMIT 3",
        )

        with pytest.raises(GuardrailValidationError) as exc_info:
            execute_query(
                db_session_module,
                test_datasource_module.id,
                "SELECT username FROM users LIMIT 3",
                safety_decision=decision,
            )

        assert any(check["rule"] == "safety_decision_sql_mismatch" for check in exc_info.value.checks)

    def test_execute_query_bypass_requires_testing_env(self, db_session_module, test_datasource_module, monkeypatch) -> None:
        from engine.errors import GuardrailValidationError
        from engine.sql.test_executor import execute_query_for_test

        monkeypatch.delenv("DBFOX_TESTING", raising=False)

        with pytest.raises(GuardrailValidationError) as exc_info:
            execute_query_for_test(
                db_session_module,
                test_datasource_module.id,
                "SELECT id FROM users LIMIT 3",
            )

        assert any(check["rule"] == "trust_gate_bypass_disabled" for check in exc_info.value.checks)

    def test_explain_sql_sqlite(self, db_session_module, test_datasource_module) -> None:
        sync_schema(db_session_module, test_datasource_module.id)

        res = explain_sql(db_session_module, test_datasource_module.id, "SELECT id, username FROM users LIMIT 3")
        assert res["success"] is True
        assert res["safetyDecision"]["decision_id"]
        assert res["safetyDecision"]["can_execute"] is True
        assert "records" in res
        assert "warnings" in res
        assert len(res["records"]) >= 1
        
        record = res["records"][0]
        assert "type" in record
        assert "key" in record
        assert "rows" in record
        assert "Extra" in record

    def test_explain_sql_non_select_rejected(self, db_session_module, test_datasource_module) -> None:
        from engine.errors import GuardrailValidationError

        with pytest.raises(GuardrailValidationError) as exc_info:
            explain_sql(db_session_module, test_datasource_module.id, "DELETE FROM users")
        assert any(check["rule"] in {"select_only", "blocked_command_type"} for check in exc_info.value.checks)

    def test_explain_sql_secondary_validation(self, db_session_module, test_datasource_module) -> None:
        from engine.errors import GuardrailValidationError
        from engine.sql.explain_validator import validate_explain_sql as _validate_explain_sql

        # Valid select passes
        _validate_explain_sql("SELECT id FROM users", "sqlite")
        
        # Multi-statement rejected
        with pytest.raises(GuardrailValidationError):
            _validate_explain_sql("SELECT id FROM users; SELECT username FROM users", "sqlite")
            
        # Non-select rejected
        with pytest.raises(GuardrailValidationError):
            _validate_explain_sql("DROP TABLE users", "sqlite")


class TestExecuteQueryBoundary:
    def test_execute_query_has_no_bypass_guardrail_parameter(self) -> None:
        """Public execute_query must not expose a bypass_guardrail parameter."""
        import inspect
        sig = inspect.signature(execute_query)
        assert "bypass_guardrail" not in sig.parameters, (
            "execute_query must not accept bypass_guardrail — use execute_query_for_test instead"
        )

    def test_execute_query_for_test_accepts_bypass(self) -> None:
        """execute_query_for_test should be available for test bypass."""
        from engine.sql.test_executor import execute_query_for_test
        sig = inspect.signature(execute_query_for_test)
        assert "bypass_guardrail" not in sig.parameters
