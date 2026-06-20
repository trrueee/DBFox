from __future__ import annotations

import pytest

from engine.tools.db_tools import (
    db_inspect,
    db_observe,
    db_preview,
    db_query,
    db_remember,
    db_search,
)
from engine.models import DomainTagRule, QueryHistory, SemanticAlias
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


def test_db_preview_rejects_unknown_columns_before_query(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    with pytest.raises(ValueError, match="Unknown column"):
        db_preview(db_session, test_datasource.id, table="users", columns=["missing"])
    assert db_session.query(QueryHistory).count() == 0


def test_db_query_revalidates_and_executes_readonly_sql(db_session, test_datasource) -> None:
    sync_schema(db_session, test_datasource.id)
    result = db_query(db_session, test_datasource.id, "SELECT id, email FROM users", question="count users")
    assert result["status"] == "success"
    assert result["columns"] == ["id", "email"]
    assert result["returned_rows"] >= 1
    assert result["audit"]["readonly_checked"] is True
    assert result["audit"]["limit_injected"] is True
    assert "LIMIT" in result["safe_sql"].upper()


def test_db_query_blocks_writes_inside_tool(db_session, test_datasource) -> None:
    from engine.errors import DBFoxError
    sync_schema(db_session, test_datasource.id)
    with pytest.raises(DBFoxError):
        db_query(db_session, test_datasource.id, "DELETE FROM users")


def test_db_remember_records_table_alias_and_redacts_evidence(db_session, test_datasource) -> None:
    result = db_remember(
        db_session,
        test_datasource.id,
        mem_type="table_alias",
        target="users",
        evidence="Found in request from alice@example.com",
        aliases=["customers"],
    )

    assert result["status"] == "remembered"
    assert result["created"] == [{"alias": "customers", "target": "users", "target_type": "table"}]
    row = (
        db_session.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == test_datasource.id,
            SemanticAlias.alias == "customers",
            SemanticAlias.target_type == "table",
            SemanticAlias.target == "users",
        )
        .one()
    )
    assert row.description == "Found in request from [REDACTED_EMAIL]"


def test_db_remember_prod_alias_requires_confirmation_without_write(db_session, test_datasource) -> None:
    test_datasource.env = "prod"
    db_session.commit()

    result = db_remember(
        db_session,
        test_datasource.id,
        mem_type="table_alias",
        target="users",
        aliases=["customers"],
    )

    assert result["status"] == "pending_confirmation"
    assert result["aliases"] == ["customers"]
    assert (
        db_session.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == test_datasource.id,
            SemanticAlias.alias == "customers",
            SemanticAlias.target_type == "table",
            SemanticAlias.target == "users",
        )
        .count()
        == 0
    )


def test_db_remember_join_path_requires_confirmation_without_write(db_session, test_datasource) -> None:
    result = db_remember(
        db_session,
        test_datasource.id,
        mem_type="join_path",
        target="orders.users",
        value={
            "left_table": "orders",
            "left_column": "user_id",
            "right_table": "users",
            "right_column": "id",
            "join_type": "many_to_one",
            "description": "orders.user_id links to users.id",
        },
    )

    assert result["status"] == "pending_confirmation"
    assert result["join"]["left_table"] == "orders"
    assert (
        db_session.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == test_datasource.id,
            SemanticAlias.target_type == "join_path",
            SemanticAlias.target == "orders.users",
        )
        .count()
        == 0
    )


def test_db_remember_business_definition_requires_confirmation_without_write(db_session, test_datasource) -> None:
    result = db_remember(
        db_session,
        test_datasource.id,
        mem_type="business_definition",
        target="active_users",
        value={
            "description": "Users with a recent login from alice@example.com",
            "sql": "SELECT * FROM users WHERE email = 'alice@example.com'",
        },
    )

    assert result["status"] == "pending_confirmation"
    assert result["definition"]["sql"] == "SELECT * FROM users WHERE email = '[REDACTED_EMAIL]'"
    assert (
        db_session.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == test_datasource.id,
            SemanticAlias.target_type == "business_definition",
            SemanticAlias.target == "active_users",
        )
        .count()
        == 0
    )
