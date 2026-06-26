import pytest
from engine.tools.db_tools import _build_preview_sql, _build_where_clause
from engine.errors import ToolInputError
from engine.sql.builder import build_where_clause

# covers: PREVIEW-1 table with backtick/injection
def test_preview1_injection_backtick():
    with pytest.raises(ToolInputError):
        _build_preview_sql("t` WHERE 1=1 --", ["id"], 10, {}, "mysql")

# covers: PREVIEW-2 table with semicolon
def test_preview2_injection_semicolon():
    with pytest.raises(ToolInputError):
        _build_preview_sql("t; DROP TABLE x", ["id"], 10, {}, "mysql")

# covers: PREVIEW-3 columns with injection
def test_preview3_columns_injection():
    with pytest.raises(ToolInputError):
        _build_preview_sql("t", ["a) OR 1=1 --"], 10, {}, "mysql")

# covers: PREVIEW-4 table and columns normal
def test_preview4_normal():
    sql = _build_preview_sql("normal_table", ["id", "name"], 10, {}, "mysql")
    assert sql == "SELECT `id`, `name` FROM `normal_table` LIMIT 10"

# covers: PREVIEW-5 dialect postgres
def test_preview5_postgres():
    sql = _build_preview_sql("normal_table", ["id", "name"], 10, {}, "postgres")
    assert sql == 'SELECT "id", "name" FROM "normal_table" LIMIT 10'

# covers: PREVIEW-6 table name with space
def test_preview6_space():
    with pytest.raises(ToolInputError):
        _build_preview_sql("my table", ["id"], 10, {}, "mysql")

# covers: PREVIEW-7 empty columns list
def test_preview7_empty_columns():
    sql = _build_preview_sql("normal_table", [], 10, {}, "mysql")
    assert sql == "SELECT * FROM `normal_table` LIMIT 10"


# covers: WHERE-1 op="=" value=None
def test_where1_null():
    res = _build_where_clause({"column": "id", "op": "=", "value": None}, "`")
    assert res == "`id` IS NULL"

# covers: WHERE-2 op="=" value=int
def test_where2_int():
    res = _build_where_clause({"column": "id", "op": "=", "value": 123}, "`")
    assert res == "`id` = 123"

# covers: WHERE-3 op="LIKE" value="%a'b%"
def test_where3_like_escape():
    res = _build_where_clause({"column": "name", "op": "LIKE", "value": "%a'b%"}, "`")
    assert res == "`name` LIKE '%a''b%'"

# covers: WHERE-4 op="IN" value=list
def test_where4_in():
    res = _build_where_clause({"column": "name", "op": "IN", "value": ["a", "b"]}, "`")
    assert res == "`name` IN ('a', 'b')"

# covers: WHERE-5 op="DELETE"
def test_where5_unsafe_op():
    with pytest.raises(ValueError) as exc:
        _build_where_clause({"column": "id", "op": "DELETE", "value": 1}, "`")
    assert "Unsafe operator" in str(exc.value)

# covers: WHERE-6 op="IN" value not list
def test_where6_in_non_list():
    res = _build_where_clause({"column": "name", "op": "IN", "value": "a"}, "`")
    assert res == "`name` IN 'a'"


def test_where_ilike_downgrades_to_like_for_sqlite():
    res = build_where_clause({"column": "name", "op": "ILIKE", "value": "%bob%"}, "sqlite")
    assert res == "\"name\" LIKE '%bob%'"


def test_where_ilike_is_preserved_for_postgres():
    res = build_where_clause({"column": "name", "op": "ILIKE", "value": "%bob%"}, "postgres")
    assert res == "\"name\" ILIKE '%bob%'"
