"""Regression tests for Guardrail bypass cases found in the architecture review."""

from engine.sql.guardrail import guardrail_check


def _rules(sql: str) -> set[str]:
    return {check["rule"] for check in guardrail_check(sql)["checks"]}


def test_current_user_blocked() -> None:
    result = guardrail_check("SELECT CURRENT_USER()")
    assert result["result"] == "reject"
    assert "dangerous_function" in _rules("SELECT CURRENT_USER()")


def test_database_and_schema_blocked() -> None:
    for sql in ["SELECT DATABASE()", "SELECT SCHEMA()"]:
        result = guardrail_check(sql)
        assert result["result"] == "reject"
        assert any(check["rule"] == "dangerous_function" for check in result["checks"])


def test_version_blocked() -> None:
    result = guardrail_check("SELECT VERSION()")
    assert result["result"] == "reject"
    assert "dangerous_function" in _rules("SELECT VERSION()")


def test_system_variable_blocked() -> None:
    result = guardrail_check("SELECT @@version")
    assert result["result"] == "reject"
    assert "system_variable_blocked" in _rules("SELECT @@version")


def test_union_auto_limit() -> None:
    result = guardrail_check("SELECT name FROM products UNION SELECT name FROM suppliers")
    assert result["result"] == "warn"
    assert "auto_limit" in _rules("SELECT name FROM products UNION SELECT name FROM suppliers")
    assert "LIMIT 1000" in result["safeSql"].upper()


def test_count_star_does_not_warn_select_star() -> None:
    result = guardrail_check("SELECT COUNT(*) FROM users LIMIT 10")
    assert result["result"] == "pass"
    assert "select_star" not in _rules("SELECT COUNT(*) FROM users LIMIT 10")


def test_table_star_warns_select_star() -> None:
    result = guardrail_check("SELECT users.* FROM users LIMIT 10")
    assert result["result"] == "warn"
    assert "select_star" in _rules("SELECT users.* FROM users LIMIT 10")


# ── MySQL executable comment bypass regression tests ──────────────────

def test_mysql_exec_comment_drop_rejected() -> None:
    """/*!50001 DROP TABLE logs;*/ must be rejected — it hides DDL in a comment."""
    result = guardrail_check("/*!50001 DROP TABLE logs;*/ SELECT 1;")
    assert result["result"] == "reject"
    assert "mysql_executable_comment" in _rules("/*!50001 DROP TABLE logs;*/ SELECT 1;")


def test_mysql_exec_comment_delete_rejected() -> None:
    result = guardrail_check("/*!50700 DELETE FROM users WHERE 1=1;*/ SELECT name FROM users;")
    assert result["result"] == "reject"
    assert "mysql_executable_comment" in _rules("/*!50700 DELETE FROM users WHERE 1=1;*/ SELECT name FROM users;")


def test_mysql_exec_comment_standalone_rejected() -> None:
    """Executable comment as the entire SQL body must be rejected."""
    result = guardrail_check("/*!50001 DROP TABLE logs;*/")
    assert result["result"] == "reject"
    assert "mysql_executable_comment" in _rules("/*!50001 DROP TABLE logs;*/")


def test_mysql_exec_comment_mid_query_rejected() -> None:
    """Executable comment embedded in a SELECT must be rejected."""
    result = guardrail_check("SELECT 1 /*!50001 UNION SELECT password FROM users;*/ FROM t;")
    assert result["result"] == "reject"
    assert "mysql_executable_comment" in _rules("SELECT 1 /*!50001 UNION SELECT password FROM users;*/ FROM t;")


def test_optimizer_hint_allowed() -> None:
    """/*+ INDEX(...) */ optimizer hints are NOT executable comments and must pass."""
    result = guardrail_check("SELECT /*+ INDEX(t idx) */ name FROM t LIMIT 10")
    assert result["result"] in ("pass", "warn")
    assert "mysql_executable_comment" not in _rules("SELECT /*+ INDEX(t idx) */ name FROM t LIMIT 10")


def test_hash_comment_delimiter() -> None:
    """MySQL # line comments must not cause false multi-statement detection."""
    from engine.sql.guardrail import count_statement_delimiters
    assert count_statement_delimiters("SELECT 1 # comment with ; inside\nFROM t;") == 1
