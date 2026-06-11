"""AI / Text-to-SQL tests — 对应第一版.md Section 18 V1.1"""
from unittest.mock import MagicMock, patch

import pytest
from engine.sql.generator import (
    build_schema_direct_prompt,
    generate_sql,
    generate_sql_from_schema_context,
)
from engine.errors import AIServiceError
from engine.models import DataSource


def test_schema_direct_prompt_is_sqlite_dialect_aware() -> None:
    system_prompt, user_prompt = build_schema_direct_prompt(
        question="How many students are there?",
        schema_context="TABLE students(id, name)",
        dialect="sqlite",
    )

    assert "SQLite SELECT" in system_prompt
    assert "MySQL" not in system_prompt
    assert "How many students are there?" in user_prompt


def test_schema_direct_prompt_contains_aggregate_and_limit_rules() -> None:
    system_prompt, _user_prompt = build_schema_direct_prompt(
        question="What is the average score?",
        schema_context="TABLE courses(score)",
        dialect="postgresql",
    )

    assert "PostgreSQL SELECT" in system_prompt
    assert 'how many", "number of", or "count", use COUNT(*)' in system_prompt
    assert 'average", "avg", or "mean", use AVG(column)' in system_prompt
    assert "Do not add LIMIT to aggregate-only queries" in system_prompt


def test_generate_sql_from_schema_context_returns_schema_direct_metadata(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class MockResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"choices": [{"message": {"content": "SELECT COUNT(*) FROM students"}}]}

    def fake_post(*_args, **kwargs):
        captured.update(kwargs)
        return MockResponse()

    monkeypatch.setattr("engine.sql.generator.httpx.post", fake_post)

    result = generate_sql_from_schema_context(
        question="How many students are there?",
        schema_context="TABLE students(id, name)",
        dialect="sqlite",
        llm_config={"api_key": "sk-test", "api_base": "https://test/v1", "model": "deepseek-test"},
    )

    messages = captured["json"]["messages"]  # type: ignore[index]
    assert "SQLite SELECT" in messages[0]["content"]
    assert "MySQL" not in messages[0]["content"]
    assert result["sql"] == "SELECT COUNT(*) FROM students"
    assert result["metadata"]["generation_source"] == "schema_direct_llm"
    assert result["metadata"]["used_renderer"] is False


def test_generate_sql_from_schema_context_without_api_key_fails_closed() -> None:
    result = generate_sql_from_schema_context(
        question="list products",
        schema_context="TABLE students(id, name)",
        dialect="sqlite",
        llm_config={},
    )

    assert result["sql"] is None
    assert result["error"] == "LLM API key required for Text-to-SQL generation"


def test_legacy_generate_sql_non_demo_without_api_key_does_not_use_demo_fallback(db_session) -> None:
    ds = DataSource(
        id="real-sqlite-no-key",
        name="real_sqlite",
        db_type="sqlite",
        host="localhost",
        port=0,
        database_name="/tmp/real.sqlite",
        username="",
        password_ciphertext="",
        password_nonce="",
        status="active",
    )
    db_session.add(ds)
    db_session.commit()

    result = generate_sql(db_session, ds.id, "list products")

    assert result["sql"] is None
    assert result["error"] == "LLM API key required for Text-to-SQL generation"



# ============================================================
# generate_sql — 在线模式（mock httpx）
# ============================================================

def test_generate_sql_online_success(db_session, test_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "```sql\nSELECT * FROM users LIMIT 10\n```"}}]
    }

    with patch("engine.sql.generator.httpx.post", return_value=mock_resp):
        result = generate_sql(db_session, test_datasource.id, "list all users",
                              llm_config={"api_key": "sk-test", "api_base": "https://test/v1",
                                          "model": "gpt-test"})
    assert result["sql"] == "SELECT * FROM users LIMIT 10"
    assert result["mode"] == "online"
    assert result["guardrail"]["result"] in ("pass", "warn", "reject")


def test_generate_sql_online_no_code_fence(db_session, test_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "SELECT id, name FROM products LIMIT 20"}}]
    }

    with patch("engine.sql.generator.httpx.post", return_value=mock_resp):
        result = generate_sql(db_session, test_datasource.id, "list products",
                              llm_config={"api_key": "sk-test"})
    assert "SELECT" in result["sql"]
    assert "products" in result["sql"]
    assert result["mode"] == "online"


def test_generate_sql_online_http_error(db_session, test_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("engine.sql.generator.httpx.post", return_value=mock_resp):
        with pytest.raises(AIServiceError, match="LLM API returned an error"):
            generate_sql(db_session, test_datasource.id, "test question",
                         llm_config={"api_key": "sk-test"})


def test_generate_sql_online_guardrail_reject(db_session, test_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "```sql\nDROP TABLE users;\n```"}}]
    }

    with patch("engine.sql.generator.httpx.post", return_value=mock_resp):
        result = generate_sql(db_session, test_datasource.id, "delete all users",
                              llm_config={"api_key": "sk-test"})
    assert result["guardrail"]["result"] == "reject"


def test_validate_sql_schema_hallucinations(db_session, test_datasource) -> None:
    from engine.sql.generator import validate_sql_schema
    from engine.models import SchemaTable, SchemaColumn

    # 1. Add some schema info to metastore
    users_tbl = SchemaTable(
        id="tbl-users",
        data_source_id=test_datasource.id,
        table_schema="demo_shop",
        table_name="users",
        table_comment="User details"
    )
    db_session.add(users_tbl)
    db_session.commit()

    db_session.add(SchemaColumn(id="col-u1", table_id="tbl-users", column_name="id", column_type="int"))
    db_session.add(SchemaColumn(id="col-u2", table_id="tbl-users", column_name="username", column_type="varchar"))
    db_session.add(SchemaColumn(id="col-u3", table_id="tbl-users", column_name="email", column_type="varchar"))
    
    orders_tbl = SchemaTable(
        id="tbl-orders",
        data_source_id=test_datasource.id,
        table_schema="demo_shop",
        table_name="orders",
        table_comment="Order details"
    )
    db_session.add(orders_tbl)
    db_session.commit()

    db_session.add(SchemaColumn(id="col-o1", table_id="tbl-orders", column_name="id", column_type="int"))
    db_session.add(SchemaColumn(id="col-o2", table_id="tbl-orders", column_name="user_id", column_type="int"))
    db_session.add(SchemaColumn(id="col-o3", table_id="tbl-orders", column_name="amount", column_type="decimal"))
    db_session.commit()

    # 2. Test valid queries
    warnings = validate_sql_schema("SELECT username, email FROM users", db_session, test_datasource.id)
    assert len(warnings) == 0

    warnings = validate_sql_schema("SELECT u.username, o.amount FROM users u JOIN orders o ON u.id = o.user_id", db_session, test_datasource.id)
    assert len(warnings) == 0

    # 3. Test hallucinated table
    warnings = validate_sql_schema("SELECT name FROM non_existent_table", db_session, test_datasource.id)
    assert len(warnings) > 0
    assert any("non_existent_table" in w for w in warnings)

    # 4. Test hallucinated column (no table prefix)
    warnings = validate_sql_schema("SELECT age FROM users", db_session, test_datasource.id)
    assert len(warnings) > 0
    assert any("age" in w for w in warnings)

    # 5. Test hallucinated column with alias prefix
    warnings = validate_sql_schema("SELECT u.username, o.non_existent_col FROM users u JOIN orders o ON u.id = o.user_id", db_session, test_datasource.id)
    assert len(warnings) > 0
    assert any("non_existent_col" in w for w in warnings)


def test_generate_sql_returns_schema_linking_metadata(db_session, test_datasource, monkeypatch) -> None:
    from engine.schema_sync import sync_schema

    class MockResponse:
        status_code = 200
        text = "ok"
        def json(self):
            return {"choices": [{"message": {"content": "SELECT SUM(o.total_amount) FROM orders o JOIN users u ON o.user_id = u.id GROUP BY u.id"}}]}

    monkeypatch.setattr("engine.sql.generator.httpx.post", lambda *a, **kw: MockResponse())

    sync_schema(db_session, test_datasource.id)
    result = generate_sql(db_session, test_datasource.id, "按客户统计 GMV", optimize_rag=True,
                          llm_config={"api_key": "sk-test", "api_base": "https://test/v1", "model": "gpt-test"})

    assert result["originalSchemaTableCount"] == 20
    assert result["selectedSchemaTableCount"] < result["originalSchemaTableCount"]
    assert "orders" in result["selectedTables"]
    assert "users" in result["selectedTables"]
    assert result["schemaContextSize"] > 0
    assert result["schemaLinkingReasons"]
    assert result["queryPlan"]["intent"] == "aggregate_order_amount"
    assert "orders" in result["queryPlan"]["tables"]
