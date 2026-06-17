"""Guardrail test suite — 对应第一版.md Section 18.1"""
import inspect

import pytest
from engine.sql.guardrail import guardrail_check, GuardrailResult


def _check(result: GuardrailResult, expected_result: str) -> None:
    """Assert guardrail result and that required fields exist."""
    assert result["result"] == expected_result
    assert "originalSql" in result
    assert "safeSql" in result
    assert "checks" in result
    assert "message" in result


def test_guardrail_check_uses_module_logger_without_function_local_logging_import() -> None:
    source = inspect.getsource(guardrail_check)

    assert "import logging" not in source


# ============================================================
# PASS — 安全 SELECT 直接通过
# ============================================================

def test_normal_select() -> None:
    _check(guardrail_check(
        "SELECT id, name FROM users WHERE status = 'active' LIMIT 10"
    ), "pass")


def test_select_with_join() -> None:
    _check(guardrail_check(
        "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id LIMIT 10"
    ), "pass")


def test_select_with_aggregation() -> None:
    _check(guardrail_check(
        "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status LIMIT 10"
    ), "pass")


def test_select_with_subquery() -> None:
    _check(guardrail_check(
        "SELECT id, name FROM users WHERE id IN (SELECT user_id FROM orders) LIMIT 10"
    ), "pass")


def test_select_with_union() -> None:
    _check(guardrail_check(
        "SELECT name FROM products UNION SELECT name FROM suppliers"
    ), "warn")


# ============================================================
# WARN — 通过但有优化建议
# ============================================================

def test_auto_limit_when_missing() -> None:
    r = guardrail_check("SELECT * FROM products")
    assert r["result"] == "warn"
    assert "LIMIT 1000" in r["safeSql"].upper()
    assert any(c["rule"] == "auto_limit" for c in r["checks"])


def test_select_star_warning() -> None:
    r = guardrail_check("SELECT * FROM products LIMIT 10")
    assert r["result"] == "warn"
    assert any(c["rule"] == "select_star" for c in r["checks"])


# ============================================================
# REJECT — DDL / DML 拦截
# ============================================================

def test_drop_blocked() -> None:
    assert guardrail_check("DROP TABLE users")["result"] == "reject"


def test_delete_blocked() -> None:
    assert guardrail_check("DELETE FROM users WHERE id = 1")["result"] == "reject"


def test_update_blocked() -> None:
    assert guardrail_check("UPDATE users SET email = 'x' WHERE id = 1")["result"] == "reject"


def test_insert_blocked() -> None:
    assert guardrail_check("INSERT INTO users (name) VALUES ('test')")["result"] == "reject"


def test_alter_blocked() -> None:
    assert guardrail_check("ALTER TABLE users ADD COLUMN age INT")["result"] == "reject"


def test_create_blocked() -> None:
    assert guardrail_check("CREATE TABLE test (id INT)")["result"] == "reject"


def test_truncate_blocked() -> None:
    assert guardrail_check("TRUNCATE TABLE users")["result"] == "reject"


# ============================================================
# REJECT — 危险操作拦截
# ============================================================

def test_call_blocked() -> None:
    assert guardrail_check("CALL my_procedure()")["result"] == "reject"


def test_multi_statement_blocked() -> None:
    r = guardrail_check("SELECT 1; DROP TABLE users;")
    assert r["result"] == "reject"
    assert any(c["rule"] == "multi_statement" for c in r["checks"])


def test_information_schema_blocked() -> None:
    assert guardrail_check("SELECT * FROM information_schema.tables")["result"] == "reject"


def test_mysql_system_schema_blocked() -> None:
    assert guardrail_check("SELECT * FROM mysql.user")["result"] == "reject"


def test_sleep_blocked() -> None:
    assert guardrail_check("SELECT SLEEP(10)")["result"] == "reject"


def test_benchmark_blocked() -> None:
    assert guardrail_check("SELECT BENCHMARK(1000000, MD5('x'))")["result"] == "reject"


def test_load_file_blocked() -> None:
    assert guardrail_check("SELECT LOAD_FILE('/etc/passwd')")["result"] == "reject"


def test_into_outfile_blocked() -> None:
    assert guardrail_check("SELECT * FROM users INTO OUTFILE '/tmp/dump'")["result"] == "reject"


def test_sql_too_long_blocked() -> None:
    assert guardrail_check("SELECT 1" + "x" * 20000)["result"] == "reject"


# ============================================================
# REJECT — 边界情况
# ============================================================

def test_empty_sql() -> None:
    r = guardrail_check("")
    assert r["result"] == "reject"
    assert any(c["rule"] == "empty_sql" for c in r["checks"])


def test_whitespace_only() -> None:
    assert guardrail_check("   ")["result"] == "reject"


def test_syntax_error() -> None:
    r = guardrail_check("BROKEN !!! NOT VALID SQL @@@ ###")
    assert r["result"] == "reject"
    assert any(c["rule"] == "syntax_error" for c in r["checks"])


def test_mysql_syntax_invalid_message_does_not_echo_broken_order_tokens() -> None:
    sql = "SELECT Name FROM singer ORDER BY [{'column': 'Age', 'direction': 'DESC'}] LIMIT 100"

    r = guardrail_check(sql)
    serialized = str(r).upper()

    assert r["result"] == "reject"
    assert any(c["rule"] == "mysql_syntax_invalid" for c in r["checks"])
    assert "ORDER BY ARRAY" not in serialized
    assert "ORDER BY STRUCT" not in serialized


# ============================================================
# NEW IN SPRINT 1: RECURSIVE CTE, ROW LOCKING, & DYNAMIC DIALECT
# ============================================================

def test_recursive_cte_blocked() -> None:
    # Standard recursive CTE query
    sql = """
    WITH RECURSIVE cte AS (
        SELECT 1 AS n
        UNION ALL
        SELECT n + 1 FROM cte WHERE n < 5
    )
    SELECT * FROM cte
    """
    r = guardrail_check(sql)
    assert r["result"] == "reject"
    assert any(c["rule"] == "recursive_cte_blocked" for c in r["checks"])


def test_row_locking_blocked() -> None:
    # SELECT ... FOR UPDATE should be rejected
    r1 = guardrail_check("SELECT * FROM users WHERE id = 1 FOR UPDATE")
    assert r1["result"] == "reject"
    assert any(c["rule"] == "row_locking_blocked" for c in r1["checks"])

    # SELECT ... FOR SHARE should also be rejected
    r2 = guardrail_check("SELECT * FROM users WHERE id = 1 FOR SHARE")
    assert r2["result"] == "reject"
    assert any(c["rule"] == "row_locking_blocked" for c in r2["checks"])


def test_dialect_specific_guardrail() -> None:
    # 1. PostgreSQL dialect verification
    # postgres dialect supports double colons :: for casting
    sql_pg = "SELECT id::text FROM users"
    r_pg = guardrail_check(sql_pg, dialect="postgres")
    assert r_pg["result"] == "warn"  # warn because of no limit, meaning it parsed perfectly!
    
    # 2. SQLite dialect verification
    # sqlite-specific master catalog access should be blocked
    r_sl = guardrail_check("SELECT * FROM sqlite_master", dialect="sqlite")
    assert r_sl["result"] == "reject"
    assert any(c["rule"] == "system_catalog_blocked" for c in r_sl["checks"])

    # 3. MySQL dialect verification
    # MySQL specific row locking syntax
    sql_my = "SELECT * FROM users FOR UPDATE"
    r_my = guardrail_check(sql_my, dialect="mysql")
    assert r_my["result"] == "reject"
    assert any(c["rule"] == "row_locking_blocked" for c in r_my["checks"])


# ============================================================
# PASS — INTERSECT / EXCEPT / UNION set operations
# ============================================================

def test_intersect_allowed() -> None:
    """INTERSECT between two SELECTs is read-only and must pass."""
    r = guardrail_check(
        "SELECT a FROM t1 INTERSECT SELECT a FROM t2"
    )
    assert r["result"] in ("pass", "warn")  # warn if auto-LIMIT injected
    assert "guardrail_reject" not in str(r.get("checks", ""))
    # Safe SQL must still contain INTERSECT
    assert "INTERSECT" in r["safeSql"].upper()


def test_except_allowed() -> None:
    """EXCEPT between two SELECTs is read-only and must pass."""
    r = guardrail_check(
        "SELECT a FROM t1 EXCEPT SELECT a FROM t2"
    )
    assert r["result"] in ("pass", "warn")
    assert "guardrail_reject" not in str(r.get("checks", ""))
    assert "EXCEPT" in r["safeSql"].upper()


def test_union_allowed() -> None:
    """UNION between two SELECTs is read-only and must pass."""
    r = guardrail_check(
        "SELECT a FROM t1 UNION SELECT a FROM t2"
    )
    assert r["result"] in ("pass", "warn")
    assert "guardrail_reject" not in str(r.get("checks", ""))


def test_intersect_with_limit() -> None:
    """INTERSECT with explicit LIMIT should pass cleanly."""
    r = guardrail_check(
        "SELECT a FROM t1 INTERSECT SELECT a FROM t2 LIMIT 50"
    )
    assert r["result"] == "pass"
    assert "INTERSECT" in r["safeSql"].upper()


def test_intersect_auto_limit_injected() -> None:
    """INTERSECT without LIMIT gets auto-LIMIT 1000."""
    r = guardrail_check(
        "SELECT a FROM t1 INTERSECT SELECT a FROM t2"
    )
    assert r["result"] == "warn"
    assert "LIMIT 1000" in r["safeSql"].upper()


# ============================================================
# REJECT — set operation with DML still blocked
# ============================================================

def test_intersect_with_drop_blocked() -> None:
    """INTERSECT followed by DROP must be rejected as multi-statement."""
    r = guardrail_check(
        "SELECT a FROM t1 INTERSECT SELECT a FROM t2; DROP TABLE t1"
    )
    assert r["result"] == "reject"
    assert any(c["rule"] == "multi_statement" for c in r["checks"])


def test_insert_still_blocked() -> None:
    """INSERT must still be rejected."""
    r = guardrail_check("INSERT INTO t VALUES (1)")
    assert r["result"] == "reject"
