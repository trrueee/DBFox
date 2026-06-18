from __future__ import annotations

from engine.tools.runtime.context import ToolContext
from engine.agent_core.types import AgentRunRequest
from engine.models import QueryHistory
from engine.schema_sync import sync_schema


def _ctx(db_session, datasource, question: str = "hello") -> ToolContext:
    return ToolContext(
        db=db_session,
        request=AgentRunRequest(datasource_id=datasource.id, question=question),
        state_view={"datasource_id": datasource.id, "question": question},
    )


def test_db_observe_returns_catalog_map(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_observe

    sync_schema(db_session, test_datasource.id)
    obs = db_observe(_ctx(db_session, test_datasource), {"mode": "overview"})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["dialect"] == "sqlite"
    assert obs.output["table_count"] >= 20
    schemas = obs.output["schemas"]
    assert schemas[0]["name"] == "main"
    users = next(t for t in schemas[0]["tables"] if t["name"] == "users")
    assert users["columns"] >= 5
    assert "user" in users["tags"]
    assert any(domain["label"] == "user" for domain in obs.output["domains"])


def test_db_observe_tables_mode_includes_connected_tables(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_observe

    sync_schema(db_session, test_datasource.id)
    obs = db_observe(_ctx(db_session, test_datasource), {"mode": "tables", "table_names": ["orders"]})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["tables"][0]["name"] == "orders"
    assert "users" in obs.output["tables"][0]["connected_tables"]
    assert obs.output["tables"][0]["primary_key"] == "id"


def test_db_search_fallback_keyword_matches_table_and_column_names(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_search

    sync_schema(db_session, test_datasource.id)

    obs = db_search(_ctx(db_session, test_datasource), {"query": "users", "limit": 5})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["total_matches"] >= 1
    first = obs.output["results"][0]
    assert first["type"] in {"table", "column"}
    assert any(result.get("table_name") == "users" for result in obs.output["results"])
    # keyword fallback returns Chinese reason labels
    assert any("匹配" in reason for result in obs.output["results"] for reason in result["reasons"])


def test_db_search_fallback_keyword_returns_empty_for_no_match(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_search

    sync_schema(db_session, test_datasource.id)
    obs = db_search(_ctx(db_session, test_datasource), {"query": "xyznonexistent12345", "limit": 5})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["total_matches"] == 0
    assert obs.output["results"] == []


def test_db_inspect_reads_live_sqlite_table_structure(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_inspect

    sync_schema(db_session, test_datasource.id)
    obs = db_inspect(_ctx(db_session, test_datasource), {"target": "orders"})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["object_type"] == "table"
    assert obs.output["name"] == "orders"
    assert any(col["name"] == "user_id" and col["foreign_key"]["table"] == "users" for col in obs.output["columns"])
    assert any(fk["column"] == "user_id" for fk in obs.output["foreign_keys_out"])
    assert obs.output["indexes"]


def test_db_inspect_reads_live_sqlite_column(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_inspect

    sync_schema(db_session, test_datasource.id)
    obs = db_inspect(_ctx(db_session, test_datasource), {"target": "orders.user_id"})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output == {
        "object_type": "column",
        "table": "orders",
        "name": "user_id",
        "type": "INTEGER",
        "nullable": False,
        "default": None,
        "primary_key": False,
        "foreign_key": {"table": "users", "column": "id"},
        "comment": "",
    }


def test_mysql_table_exists_uses_cursor_fetchone_after_execute() -> None:
    from engine.tools.db_tools import _mysql_table_exists

    class FakeCursor:
        def __init__(self) -> None:
            self.executed: tuple[str, tuple[str, str]] | None = None

        def execute(self, sql: str, params: tuple[str, str]) -> int:
            self.executed = (sql, params)
            return 1

        def fetchone(self) -> tuple[int]:
            return (1,)

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def cursor(self) -> FakeCursor:
            return self.cursor_obj

    conn = FakeConnection()

    assert _mysql_table_exists(conn, "app_db", "users") is True
    assert conn.cursor_obj.executed is not None
    assert conn.cursor_obj.executed[1] == ("app_db", "users")


def test_mysql_table_payload_accepts_dict_cursor_rows(db_session) -> None:
    from engine.tools.db_tools import _mysql_table_payload

    class FakeCursor:
        def __init__(self) -> None:
            self.rows: list[dict[str, object]] = []

        def execute(self, sql: str, _params=None) -> int:
            if "information_schema.COLUMNS" in sql:
                self.rows = [
                    {
                        "COLUMN_NAME": "id",
                        "DATA_TYPE": "bigint",
                        "IS_NULLABLE": "NO",
                        "COLUMN_DEFAULT": None,
                        "COLUMN_COMMENT": "primary id",
                        "is_pk": 1,
                        "REFERENCED_TABLE_NAME": None,
                        "REFERENCED_COLUMN_NAME": None,
                    },
                    {
                        "COLUMN_NAME": "tool_name",
                        "DATA_TYPE": "varchar",
                        "IS_NULLABLE": "NO",
                        "COLUMN_DEFAULT": None,
                        "COLUMN_COMMENT": "tool display name",
                        "is_pk": 0,
                        "REFERENCED_TABLE_NAME": None,
                        "REFERENCED_COLUMN_NAME": None,
                    },
                ]
            elif "REFERENCED_TABLE_NAME = %s" in sql:
                self.rows = []
            elif sql.startswith("SHOW INDEX"):
                self.rows = [
                    {"Key_name": "PRIMARY", "Non_unique": 0, "Column_name": "id"},
                ]
            elif "TABLE_ROWS" in sql:
                self.rows = [{"TABLE_ROWS": 19}]
            elif "TABLE_COMMENT" in sql:
                self.rows = [{"TABLE_COMMENT": "AI tools registry"}]
            else:
                self.rows = []
            return len(self.rows)

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

    payload = _mysql_table_payload(db_session, FakeConnection(), "ds-1", "app_db", "ai_tools")

    assert payload["name"] == "ai_tools"
    assert payload["row_estimate"] == 19
    assert payload["comment"] == "AI tools registry"
    assert payload["primary_key"] == ["id"]
    assert payload["columns"][1]["name"] == "tool_name"
    assert payload["indexes"] == [{"name": "PRIMARY", "columns": ["id"], "unique": True}]


def test_db_preview_limits_columns_rows_and_masks_sensitive_values(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_preview

    sync_schema(db_session, test_datasource.id)
    obs = db_preview(
        _ctx(db_session, test_datasource),
        {"table": "users", "columns": ["id", "email", "phone"], "limit": 50},
    )

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["table"] == "users"
    assert obs.output["columns"] == ["id", "email", "phone"]
    assert obs.output["limit_applied"] == 20
    assert obs.output["returned_rows"] <= 20
    assert obs.output["rows"][0]["email"] == "[REDACTED_EMAIL]"
    assert "column_summaries" in obs.output
    assert db_session.query(QueryHistory).filter(QueryHistory.data_source_id == test_datasource.id).count() == 1


def test_db_preview_rejects_unknown_columns_before_query(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_preview

    sync_schema(db_session, test_datasource.id)
    obs = db_preview(_ctx(db_session, test_datasource), {"table": "users", "columns": ["missing"]})

    assert obs.status == "failed"
    assert "Unknown column" in str(obs.error)
    assert db_session.query(QueryHistory).count() == 0


def test_db_query_revalidates_and_executes_readonly_sql(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_query

    sync_schema(db_session, test_datasource.id)
    obs = db_query(_ctx(db_session, test_datasource, "count users"), {"sql": "SELECT id, email FROM users"})

    assert obs.status == "success"
    assert obs.output is not None
    assert obs.output["status"] == "success"
    assert obs.output["columns"] == ["id", "email"]
    assert obs.output["returned_rows"] >= 1
    assert obs.output["audit"]["readonly_checked"] is True
    assert obs.output["audit"]["limit_injected"] is True
    assert "LIMIT" in obs.output["safe_sql"].upper()


def test_db_query_blocks_writes_inside_tool(db_session, test_datasource) -> None:
    from engine.tools.db_tools import db_query

    sync_schema(db_session, test_datasource.id)
    obs = db_query(_ctx(db_session, test_datasource), {"sql": "DELETE FROM users"})

    assert obs.status == "failed"
    assert obs.output is not None
    assert obs.output["status"] == "blocked"
    assert any(check["rule"] == "select_only" for check in obs.output["checks"])
