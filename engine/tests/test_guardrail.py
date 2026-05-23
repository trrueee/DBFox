"""Guardrail test suite — 对应第一版.md Section 18.1"""
import pytest
from engine.guardrail import guardrail_check, GuardrailResult


def _check(result: GuardrailResult, expected_result: str) -> None:
    """Assert guardrail result and that required fields exist."""
    assert result["result"] == expected_result
    assert "originalSql" in result
    assert "safeSql" in result
    assert "checks" in result
    assert "message" in result


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
