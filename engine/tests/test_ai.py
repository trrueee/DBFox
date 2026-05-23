"""AI / Text-to-SQL tests — 对应第一版.md Section 18 V1.1"""
from unittest.mock import MagicMock, patch

import pytest
from engine.ai import search_demo_sql, generate_sql, DEMO_TRANSLATIONS
from engine.errors import AIServiceError


# ============================================================
# search_demo_sql — 离线模式（无 API key）
# ============================================================

def test_offline_exact_match() -> None:
    result = search_demo_sql("所有用户")
    assert "SELECT" in result
    assert "users" in result.lower()


def test_offline_fuzzy_match() -> None:
    result = search_demo_sql("统计用户数")
    assert "COUNT" in result.upper()
    assert "users" in result.lower()


def test_offline_unknown_question() -> None:
    result = search_demo_sql("火星上有什么东西")
    assert "SELECT" in result
    assert "LIMIT 10" in result.upper()


def test_offline_all_questions_return_sql() -> None:
    for question, expected_sql in DEMO_TRANSLATIONS.items():
        result = search_demo_sql(question)
        assert "SELECT" in result, f"Key '{question}' did not produce SELECT"


# ============================================================
# generate_sql — 离线模式
# ============================================================

def test_generate_sql_offline_mode(db_session, demo_datasource) -> None:
    result = generate_sql(db_session, demo_datasource.id, "所有用户")
    assert "sql" in result
    assert "guardrail" in result
    assert result["mode"] == "offline"


def test_generate_sql_guardrail_applied(db_session, demo_datasource) -> None:
    result = generate_sql(db_session, demo_datasource.id, "所有用户")
    guard = result["guardrail"]
    assert guard["result"] in ("pass", "warn", "reject")
    assert "safeSql" in guard
    assert "checks" in guard


# ============================================================
# generate_sql — 在线模式（mock httpx）
# ============================================================

def test_generate_sql_online_success(db_session, demo_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "```sql\nSELECT * FROM users LIMIT 10\n```"}}]
    }

    with patch("engine.ai.httpx.post", return_value=mock_resp):
        result = generate_sql(db_session, demo_datasource.id, "list all users",
                              llm_config={"api_key": "sk-test", "api_base": "https://test/v1",
                                          "model": "gpt-test"})
    assert result["sql"] == "SELECT * FROM users LIMIT 10"
    assert result["mode"] == "online"
    assert result["guardrail"]["result"] in ("pass", "warn", "reject")


def test_generate_sql_online_no_code_fence(db_session, demo_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "SELECT id, name FROM products LIMIT 20"}}]
    }

    with patch("engine.ai.httpx.post", return_value=mock_resp):
        result = generate_sql(db_session, demo_datasource.id, "list products",
                              llm_config={"api_key": "sk-test"})
    assert "SELECT" in result["sql"]
    assert "products" in result["sql"]
    assert result["mode"] == "online"


def test_generate_sql_online_http_error(db_session, demo_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("engine.ai.httpx.post", return_value=mock_resp):
        with pytest.raises(AIServiceError, match="LLM API returned an error"):
            generate_sql(db_session, demo_datasource.id, "test question",
                         llm_config={"api_key": "sk-test"})


def test_generate_sql_online_guardrail_reject(db_session, demo_datasource) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "```sql\nDROP TABLE users;\n```"}}]
    }

    with patch("engine.ai.httpx.post", return_value=mock_resp):
        result = generate_sql(db_session, demo_datasource.id, "delete all users",
                              llm_config={"api_key": "sk-test"})
    assert result["guardrail"]["result"] == "reject"


def test_validate_sql_schema_hallucinations(db_session, demo_datasource) -> None:
    from engine.ai import validate_sql_schema
    from engine.models import SchemaTable, SchemaColumn

    # 1. Add some schema info to metastore
    users_tbl = SchemaTable(
        id="tbl-users",
        data_source_id=demo_datasource.id,
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
        data_source_id=demo_datasource.id,
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
    warnings = validate_sql_schema("SELECT username, email FROM users", db_session, demo_datasource.id)
    assert len(warnings) == 0

    warnings = validate_sql_schema("SELECT u.username, o.amount FROM users u JOIN orders o ON u.id = o.user_id", db_session, demo_datasource.id)
    assert len(warnings) == 0

    # 3. Test hallucinated table
    warnings = validate_sql_schema("SELECT name FROM non_existent_table", db_session, demo_datasource.id)
    assert len(warnings) > 0
    assert any("non_existent_table" in w for w in warnings)

    # 4. Test hallucinated column (no table prefix)
    warnings = validate_sql_schema("SELECT age FROM users", db_session, demo_datasource.id)
    assert len(warnings) > 0
    assert any("age" in w for w in warnings)

    # 5. Test hallucinated column with alias prefix
    warnings = validate_sql_schema("SELECT u.username, o.non_existent_col FROM users u JOIN orders o ON u.id = o.user_id", db_session, demo_datasource.id)
    assert len(warnings) > 0
    assert any("non_existent_col" in w for w in warnings)
