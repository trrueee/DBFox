from __future__ import annotations

import sqlite3

import pytest

from engine.tools.db_tools import (
    db_inspect,
    db_observe,
    db_preview,
    db_search,
    sql_execute_readonly,
    sql_validate,
)
from engine.models import DomainTagRule, QueryHistory, SchemaSearchDoc
from engine.schema_sync import sync_schema


def _ensure_default_rules(db_session, datasource_id: str) -> None:
    default_patterns = [
        ("user", ["user", "member", "customer", "account"]),
        ("order", ["order", "cart", "coupon"]),
        ("product", ["product", "category", "sku", "inventory", "item"]),
        ("payment", ["payment", "pay", "refund", "transaction"]),
        ("shipping", ["shipping", "address", "carrier", "logistics"]),
        ("analytics", ["analytics", "click", "recommendation", "event", "log"]),
        ("system", ["system", "admin", "setting", "config"]),
        ("content", ["article", "post", "comment", "review", "tag"]),
    ]
    for tag, needles in default_patterns:
        for needle in needles:
            db_session.add(DomainTagRule(data_source_id=datasource_id, pattern=needle, tag=tag, priority=10))
    db_session.commit()


def test_db_observe_returns_catalog_map(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    _ensure_default_rules(db_session, test_datasource.id)
    result = db_observe(db_session, test_datasource.id)
    assert result["dialect"] == "sqlite"
    assert result["table_count"] >= 20
    schemas = result["schemas"]
    assert schemas[0]["name"] == "main"
    users = next(t for t in schemas[0]["tables"] if t["name"] == "users")
    assert users["columns"] >= 5
    assert "user" in users["tags"]
    assert any(domain["label"] == "user" for domain in result["domains"])


def test_db_observe_tables_mode_includes_connected_tables(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_observe(db_session, test_datasource.id)
    orders = next(t for t in result["schemas"][0]["tables"] if t["name"] == "orders")
    assert "users" in orders["connected_tables"]
    assert orders["primary_key"] == ["id"]


def test_db_search_fallback_keyword_matches_table_and_column_names(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_search(db_session, test_datasource.id, "users", 5)
    assert result["total_matches"] >= 1
    first = result["results"][0]
    assert first["type"] in {"table", "column"}
    assert any(r.get("table_name") == "users" for r in result["results"])


def test_db_search_fallback_keyword_returns_empty_for_no_match(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_search(db_session, test_datasource.id, "xyznonexistent12345", 5)
    assert result["total_matches"] == 0
    assert result["results"] == []


def test_db_search_fallback_uses_schema_doc_ai_annotations(db_session, test_datasource) -> None:
    db_session.add(
        SchemaSearchDoc(
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id="orders-doc",
            table_name="orders",
            name="orders",
            ai_description="Gross merchandise value (GMV) derived from paid order amount.",
            business_terms='["GMV", "gross merchandise value"]',
            aliases='["gross sales"]',
            search_text="orders GMV gross merchandise value paid order amount",
        )
    )
    db_session.commit()

    result = db_search(db_session, test_datasource.id, "GMV", 5)

    assert result["total_matches"] >= 1
    assert result["results"][0]["table_name"] == "orders"
    assert "ai_description_match:GMV" in result["results"][0]["reasons"]


def test_db_search_fallback_uses_schema_doc_semantic_fields(db_session, test_datasource) -> None:
    db_session.add(
        SchemaSearchDoc(
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id="semantic-doc",
            table_name="orders",
            name="orders",
            semantic_tags='["revenue_metrics"]',
            business_terms='["GMV"]',
            aliases='["gross sales"]',
            search_text="orders",
        )
    )
    db_session.commit()

    for query in ("revenue_metrics", "GMV", "gross sales"):
        result = db_search(db_session, test_datasource.id, query, 5)

        assert result["total_matches"] >= 1
        assert result["results"][0]["table_name"] == "orders"


def test_db_search_returns_trace_fields_for_schema_discovery(db_session, test_datasource) -> None:
    db_session.add(
        SchemaSearchDoc(
            datasource_id=test_datasource.id,
            entity_type="table",
            entity_id="semantic-trace-doc",
            table_name="orders",
            name="orders",
            semantic_tags='["revenue_metrics"]',
            business_terms='["GMV"]',
            aliases='["gross sales"]',
            search_text="orders",
        )
    )
    db_session.commit()

    result = db_search(db_session, test_datasource.id, "revenue_metrics", 5)

    assert result["original_query"] == "revenue_metrics"
    assert result["tokens"] == ["revenue_metrics"]
    assert "semantic_tags" in result["searched_fields"]
    assert "business_terms" in result["searched_fields"]
    assert "aliases" in result["searched_fields"]
    assert result["matched_fields"] == ["semantic_tags"]
    assert result["results"][0]["matched_fields"] == ["semantic_tags"]


def test_db_inspect_reads_live_sqlite_table_structure(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_inspect(db_session, test_datasource.id, "orders")
    assert result["object_type"] == "table"
    assert result["name"] == "orders"
    assert any(col["name"] == "user_id" and col["foreign_key"]["table"] == "users" for col in result["columns"])
    assert any(fk["column"] == "user_id" for fk in result["foreign_keys_out"])
    assert result["indexes"]


def test_db_inspect_reads_live_sqlite_column(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_inspect(db_session, test_datasource.id, "orders.user_id")
    assert result == {
        "object_type": "column", "table": "orders", "name": "user_id",
        "type": "INTEGER", "nullable": False, "default": None,
        "primary_key": False, "foreign_key": {"table": "users", "column": "id"}, "comment": "",
    }


def test_mysql_table_exists_uses_cursor_fetchone_after_execute() -> None:
    from engine.tools.db_tools import _mysql_table_exists

    executed_params: list[tuple] = []

    class FakeCursor:
        def execute(self, sql: str, params: tuple[str, str]) -> int:
            executed_params.append((sql, params))
            return 1
        def fetchone(self) -> tuple[int]:
            return (1,)

    class FakeConnection:
        def cursor(self): return FakeCursor()
        @property
        def cursor_obj(self): return self._c or FakeCursor()

    conn = FakeConnection()
    conn._c = FakeCursor()
    assert _mysql_table_exists(conn, "app_db", "users") is True
    assert len(executed_params) == 1
    assert executed_params[0][1] == ("app_db", "users")


def test_mysql_table_payload_accepts_dict_cursor_rows(db_session) -> None:
    from engine.tools.db_tools import _mysql_table_payload

    class FakeCursor:
        def __init__(self) -> None:
            self.rows: list[dict[str, object]] = []
        def execute(self, sql: str, _params=None) -> int:
            if "information_schema.COLUMNS" in sql:
                self.rows = [
                    {"COLUMN_NAME": "id", "DATA_TYPE": "bigint", "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "COLUMN_COMMENT": "primary id", "is_pk": 1, "REFERENCED_TABLE_NAME": None, "REFERENCED_COLUMN_NAME": None},
                    {"COLUMN_NAME": "tool_name", "DATA_TYPE": "varchar", "IS_NULLABLE": "NO", "COLUMN_DEFAULT": None, "COLUMN_COMMENT": "tool display name", "is_pk": 0, "REFERENCED_TABLE_NAME": None, "REFERENCED_COLUMN_NAME": None},
                ]
            elif "REFERENCED_TABLE_NAME = %s" in sql:
                self.rows = []
            elif sql.startswith("SHOW INDEX"):
                self.rows = [{"Key_name": "PRIMARY", "Non_unique": 0, "Column_name": "id"}]
            elif "TABLE_ROWS" in sql:
                self.rows = [{"TABLE_ROWS": 19}]
            elif "TABLE_COMMENT" in sql:
                self.rows = [{"TABLE_COMMENT": "AI tools registry"}]
            else:
                self.rows = []
            return len(self.rows)
        def fetchall(self): return self.rows
        def fetchone(self): return self.rows[0] if self.rows else None

    class FakeConnection:
        def cursor(self) -> FakeCursor: return FakeCursor()

    payload = _mysql_table_payload(db_session, FakeConnection(), "ds-1", "app_db", "ai_tools")
    assert payload["name"] == "ai_tools"
    assert payload["row_estimate"] == 19
    assert payload["comment"] == "AI tools registry"
    assert payload["primary_key"] == ["id"]
    assert payload["columns"][1]["name"] == "tool_name"
    assert payload["indexes"] == [{"name": "PRIMARY", "columns": ["id"], "unique": True}]


def test_db_preview_limits_columns_rows_and_masks_sensitive_values(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_preview(db_session, test_datasource.id, table="users", columns=["id", "email", "phone"], limit=50)
    assert result["table"] == "users"
    assert result["columns"] == ["id", "email", "phone"]
    assert result["limit_applied"] == 20
    assert result["returned_rows"] <= 20
    assert result["rows"][0]["email"] == "[REDACTED_EMAIL]"
    assert "column_summaries" in result
    assert db_session.query(QueryHistory).filter(QueryHistory.data_source_id == test_datasource.id).count() == 1


def test_db_preview_quotes_spider_style_column_names(db_session, test_datasource) -> None:
    conn = sqlite3.connect(test_datasource.database_name)
    try:
        conn.execute(
            'CREATE TABLE spider_ratings ('
            '"18_49_Rating_Share" REAL, '
            '"Official_ratings_(millions)" REAL'
            ')'
        )
        conn.execute(
            'INSERT INTO spider_ratings ("18_49_Rating_Share", "Official_ratings_(millions)") VALUES (?, ?)',
            (4.2, 7.5),
        )
        conn.commit()
    finally:
        conn.close()

    sync_schema(db_session, test_datasource.id)

    result = db_preview(
        db_session,
        test_datasource.id,
        table="spider_ratings",
        columns=["18_49_Rating_Share", "Official_ratings_(millions)"],
        limit=5,
    )

    assert result["columns"] == ["18_49_Rating_Share", "Official_ratings_(millions)"]
    assert result["returned_rows"] == 1
    assert float(result["rows"][0]["18_49_Rating_Share"]) == 4.2
    assert float(result["rows"][0]["Official_ratings_(millions)"]) == 7.5
    assert '"18_49_Rating_Share"' in result["safe_sql"]


def test_db_preview_rejects_unknown_columns_before_query(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    with pytest.raises(ValueError, match="Unknown column"):
        db_preview(db_session, test_datasource.id, table="users", columns=["missing"])
    assert db_session.query(QueryHistory).count() == 0


def test_sql_lifecycle_validates_and_executes_readonly_sql(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    safety = sql_validate(db_session, test_datasource.id, "SELECT id, email FROM users", question="count users")
    result = sql_execute_readonly(
        db_session,
        test_datasource.id,
        question="count users",
        safety=safety["execution_safety_decision"],
    )
    assert result["status"] == "success"
    assert result["columns"] == ["id", "email"]
    assert result["returned_rows"] >= 1
    assert result["audit"]["readonly_checked"] is True
    assert result["audit"]["limit_injected"] is True
    assert "LIMIT" in result["safe_sql"].upper()


def test_sql_lifecycle_blocks_writes_inside_execute_tool(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    safety = sql_validate(db_session, test_datasource.id, "DELETE FROM users")
    with pytest.raises(RuntimeError):
        sql_execute_readonly(
            db_session,
            test_datasource.id,
            safety=safety["execution_safety_decision"],
        )
