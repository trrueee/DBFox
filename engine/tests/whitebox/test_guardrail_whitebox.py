import pytest
from engine.sql.guardrail import guardrail_check, count_statement_delimiters

# covers: G1 empty_sql
def test_g1_empty_sql():
    res = guardrail_check("", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "empty_sql" for c in res["checks"])

# covers: G2 sql_too_long
def test_g2_sql_too_long():
    res = guardrail_check("SELECT " + "1" * 20000, "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "sql_too_long" for c in res["checks"])

# covers: G2b length border
def test_g2b_length_border():
    sql = "SELECT " + "1" * 19990
    res = guardrail_check(sql, "mysql")
    assert not any(c["rule"] == "sql_too_long" for c in res["checks"])

# covers: G3 multi_statement
def test_g3_multi_statement():
    res = guardrail_check("SELECT 1; SELECT 2", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "multi_statement" for c in res["checks"])

# covers: G4 tail semicolon
def test_g4_tail_semicolon():
    res = guardrail_check("SELECT 1;", "mysql")
    assert res["result"] in ("pass", "warn")

# covers: G5 semicolon in comment
def test_g5_semicolon_in_comment():
    res = guardrail_check("SELECT 1 -- ; \n", "mysql")
    assert res["result"] in ("pass", "warn")

# covers: G6 semicolon in literal
def test_g6_semicolon_in_literal():
    res = guardrail_check("SELECT ';' FROM t", "mysql")
    assert res["result"] in ("pass", "warn")

# covers: G7 union select only
def test_g7_union_select_only():
    res = guardrail_check("SELECT 1 UNION DELETE FROM t", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] in ("select_only", "syntax_error") for c in res["checks"])

# covers: G8 nested delete subquery
def test_g8_nested_delete():
    res = guardrail_check("SELECT * FROM (DELETE FROM t) x", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] in ("select_only", "blocked_command_type", "syntax_error") for c in res["checks"])

# covers: G8b drop table
def test_g8b_drop_table():
    res = guardrail_check("DROP TABLE t", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "select_only" for c in res["checks"])

# covers: G-syntax syntax error
def test_g_syntax_error():
    res = guardrail_check("SELECTT 1 FROM", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "syntax_error" for c in res["checks"])

# covers: G9 recursive cte
def test_g9_recursive_cte():
    res = guardrail_check("WITH RECURSIVE x AS (SELECT 1 UNION SELECT 2) SELECT * FROM x", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "recursive_cte_blocked" for c in res["checks"])

# covers: G10 row locking
def test_g10_row_locking():
    res = guardrail_check("SELECT * FROM t FOR UPDATE", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "row_locking_blocked" for c in res["checks"])

# covers: G11 system catalog db
def test_g11_system_catalog_db():
    res = guardrail_check("SELECT * FROM mysql.user", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "system_catalog_blocked" for c in res["checks"])

# covers: G11b system catalog table
def test_g11b_system_catalog_table():
    res = guardrail_check("SELECT * FROM information_schema.tables", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "system_catalog_blocked" for c in res["checks"])

# covers: G12 dangerous function
def test_g12_dangerous_function():
    res = guardrail_check("SELECT SLEEP(5)", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "dangerous_function" for c in res["checks"])

# covers: G12b dangerous expression current_user
def test_g12b_dangerous_expression():
    res = guardrail_check("SELECT CURRENT_USER()", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "dangerous_function" for c in res["checks"])

# covers: G13 system variable version
def test_g13_system_variable():
    res = guardrail_check("SELECT @@version", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] == "system_variable_blocked" for c in res["checks"])

# covers: G14 into outfile
def test_g14_into_outfile():
    res = guardrail_check("SELECT * INTO OUTFILE '/x' FROM t", "mysql")
    assert res["result"] == "reject"
    assert any(c["rule"] in ("into_outfile_blocked", "syntax_error") for c in res["checks"])

# covers: G15 auto limit
def test_g15_auto_limit():
    res = guardrail_check("SELECT id FROM t", "mysql")
    assert any(c["rule"] == "auto_limit" for c in res["checks"])
    assert "LIMIT" in res["safeSql"]

# covers: G16 select star
def test_g16_select_star():
    res = guardrail_check("SELECT * FROM t LIMIT 1", "mysql")
    assert res["result"] == "warn"
    assert any(c["rule"] == "select_star" for c in res["checks"])

# covers: G17 count star exclusion
def test_g17_count_star():
    res = guardrail_check("SELECT COUNT(*) FROM t", "mysql")
    assert not any(c["rule"] == "select_star" for c in res["checks"])

# covers: G18 array syntax invalid
def test_g18_array_syntax():
    res = guardrail_check("SELECT ARRAY(SELECT 1)", "mysql")
    assert res["result"] == "reject"

# covers: G-pass normal select
def test_g_pass():
    res = guardrail_check("SELECT id FROM t LIMIT 5", "mysql")
    assert res["result"] == "pass"
    assert not res["checks"]


# covers: DELIM-1 no semicolon
def test_delim1():
    assert count_statement_delimiters("SELECT 1") == 0

# covers: DELIM-2 single semicolon
def test_delim2():
    assert count_statement_delimiters("SELECT 1;") == 1

# covers: DELIM-3 multi semicolon
def test_delim3():
    assert count_statement_delimiters("SELECT 1; SELECT 2;") == 2

# covers: DELIM-4 semicolon in single quotes
def test_delim4():
    assert count_statement_delimiters("SELECT ';' FROM t") == 0

# covers: DELIM-5 semicolon in double quotes
def test_delim5():
    assert count_statement_delimiters('SELECT "a;b" FROM t') == 0

# covers: DELIM-6 semicolon in backticks
def test_delim6():
    assert count_statement_delimiters("SELECT `a;b` FROM t") == 0

# covers: DELIM-7 escaped quote
def test_delim7():
    assert count_statement_delimiters("SELECT '\\';' FROM t") == 0

# covers: DELIM-8 comment strip
def test_delim8():
    assert count_statement_delimiters("SELECT 1 -- ; \n SELECT 2") == 0

# covers: DELIM-9 multiline comment strip
def test_delim9():
    assert count_statement_delimiters("/* a;b */ SELECT 1") == 0

# covers: DELIM-10 not a comment
def test_delim10():
    assert count_statement_delimiters("SELECT --word;") == 1


def test_legal_sql_golden_set():
    import os
    base_dir = os.path.dirname(os.path.dirname(__file__))
    fixtures_path = os.path.join(base_dir, "fixtures", "legal_sql_golden.txt")
    with open(fixtures_path, "r", encoding="utf-8") as f:
        sqls = [line.strip() for line in f if line.strip()]

    for sql in sqls:
        res = guardrail_check(sql, "mysql")
        assert res["result"] != "reject", f"Legal SQL rejected: {sql} | checks: {res['checks']}"


def test_rejected_sql_golden_set():
    import os
    base_dir = os.path.dirname(os.path.dirname(__file__))
    fixtures_path = os.path.join(base_dir, "fixtures", "rejected_sql_golden.txt")
    with open(fixtures_path, "r", encoding="utf-8") as f:
        sqls = [line.strip() for line in f if line.strip()]

    for sql in sqls:
        res = guardrail_check(sql, "mysql")
        assert res["result"] == "reject", f"Rejected SQL was not rejected: {sql} | result: {res['result']}"

