import pytest
import duckdb
import sqlite3

from dlcs.dbfox_data.backend.sql.sql_backed_view import (
    SqlBackedFilter,
    SqlBackedSort,
    SqlBackedViewError,
    build_sql_backed_page_sql,
    build_sql_backed_count_sql,
)


def compact(sql: str) -> str:
    return " ".join(sql.split())


def test_builds_filtered_sorted_paginated_sql() -> None:
    result = build_sql_backed_page_sql(
        base_sql="SELECT id, name, total FROM orders",
        dialect="mysql",
        columns=["id", "name", "total"],
        filters=[SqlBackedFilter(column="total", operator="gte", value=100)],
        search="acme",
        searchable_columns=["name"],
        sorts=[SqlBackedSort(column="total", direction="desc")],
        limit=26,
        offset=25,
    )

    sql = compact(result.sql)
    assert "FROM (SELECT id, name, total FROM orders) AS dbfox_result" in sql
    assert "`total` >= 100" in sql
    assert "CAST(`name` AS CHAR) LIKE '%acme%'" in sql
    assert "ORDER BY `total` DESC" in sql
    assert "LIMIT 26" in sql
    assert "OFFSET 25" in sql


def test_builds_multiple_filter_operators() -> None:
    result = build_sql_backed_page_sql(
        base_sql="SELECT id, name, status, deleted_at FROM users",
        dialect="mysql",
        columns=["id", "name", "status", "deleted_at"],
        filters=[
            SqlBackedFilter(column="name", operator="contains", value="li"),
            SqlBackedFilter(column="status", operator="in", value=["active", "trial"]),
            SqlBackedFilter(column="deleted_at", operator="is_null"),
        ],
        limit=20,
        offset=0,
    )

    sql = compact(result.sql)
    assert "`name` LIKE '%li%'" in sql
    assert "`status` IN ('active', 'trial')" in sql
    assert "`deleted_at` IS NULL" in sql


def test_builds_paginated_sql_from_readonly_union() -> None:
    result = build_sql_backed_page_sql(
        base_sql=(
            "SELECT id, status FROM current_orders "
            "UNION ALL SELECT id, status FROM archived_orders"
        ),
        dialect="mysql",
        columns=["id", "status"],
        sorts=[SqlBackedSort(column="id", direction="asc")],
        limit=21,
        offset=20,
    )

    sql = compact(result.sql)
    assert "FROM (SELECT id, status FROM current_orders UNION ALL SELECT id, status FROM archived_orders) AS dbfox_result" in sql
    assert "`id` ASC" in sql
    assert "LIMIT 21" in sql
    assert "OFFSET 20" in sql


def test_rejects_filter_column_outside_source_columns() -> None:
    with pytest.raises(SqlBackedViewError) as exc_info:
        build_sql_backed_page_sql(
            base_sql="SELECT id, name FROM users",
            dialect="mysql",
            columns=["id", "name"],
            filters=[SqlBackedFilter(column="password", operator="contains", value="x")],
            limit=20,
            offset=0,
        )

    assert exc_info.value.code == "FILTER_COLUMN_NOT_ALLOWED"


def test_rejects_sort_column_outside_source_columns() -> None:
    with pytest.raises(SqlBackedViewError) as exc_info:
        build_sql_backed_page_sql(
            base_sql="SELECT id, name FROM users",
            dialect="mysql",
            columns=["id", "name"],
            sorts=[SqlBackedSort(column="password", direction="asc")],
            limit=20,
            offset=0,
        )

    assert exc_info.value.code == "SORT_COLUMN_NOT_ALLOWED"


def test_rejects_unknown_filter_operator() -> None:
    with pytest.raises(SqlBackedViewError) as exc_info:
        build_sql_backed_page_sql(
            base_sql="SELECT id, name FROM users",
            dialect="mysql",
            columns=["id", "name"],
            filters=[SqlBackedFilter(column="name", operator="raw_sql", value="1=1")],
            limit=20,
            offset=0,
        )

    assert exc_info.value.code == "FILTER_OPERATOR_NOT_ALLOWED"


def test_rejects_non_select_base_sql() -> None:
    with pytest.raises(SqlBackedViewError) as exc_info:
        build_sql_backed_page_sql(
            base_sql="DELETE FROM users",
            dialect="mysql",
            columns=["id", "name"],
            limit=20,
            offset=0,
        )

    assert exc_info.value.code == "SOURCE_SQL_VALIDATION_FAILED"


@pytest.mark.parametrize("search,expected", [("通识", ["通识教育"]), ("38", ["公共基础"]), ("不存在", [])])
def test_global_search_reads_mixed_text_decimal_and_integer_columns(search, expected):
    with duckdb.connect(":memory:") as connection:
        connection.execute("CREATE TABLE credits(module VARCHAR, credits DECIMAL(8,2), courses INTEGER)")
        connection.execute("INSERT INTO credits VALUES ('通识教育',35.5,28),('公共基础',38,10)")
        options = dict(base_sql="SELECT module, credits, courses FROM credits", dialect="duckdb",
                       columns=["module", "credits", "courses"], search=search)
        page = connection.execute(build_sql_backed_page_sql(**options).sql).fetchall()
        count = connection.execute(build_sql_backed_count_sql(**options).sql).fetchone()[0]
    assert [row[0] for row in page] == expected
    assert count == len(expected)


@pytest.mark.parametrize("dialect", ["sqlite", "duckdb"])
@pytest.mark.parametrize("operator", ["contains", "starts_with", "ends_with", "search"])
@pytest.mark.parametrize("needle", ["%", "_", "!", "a!%_", "' OR 1=1 --"])
def test_literal_search_and_filter_patterns(dialect, operator, needle):
    """SQL-backed pages and counts keep the snapshot's literal string semantics."""
    values = [needle, "other", "aXYZ", "a!xx", "prefix" + needle, needle + "suffix"]
    with (sqlite3.connect(":memory:") if dialect == "sqlite" else duckdb.connect(":memory:")) as connection:
        connection.execute("CREATE TABLE patterns(value TEXT)")
        connection.executemany("INSERT INTO patterns VALUES (?)", [(value,) for value in values])
        options = dict(base_sql="SELECT value FROM patterns", dialect=dialect, columns=["value"])
        if operator == "search":
            options["search"] = needle
        else:
            options["filters"] = [SqlBackedFilter(column="value", operator=operator, value=needle)]
        actual = [row[0] for row in connection.execute(build_sql_backed_page_sql(**options).sql).fetchall()]
        count = connection.execute(build_sql_backed_count_sql(**options).sql).fetchone()[0]
    match = {
        "contains": lambda value: needle in value,
        "search": lambda value: needle in value,
        "starts_with": lambda value: value.startswith(needle),
        "ends_with": lambda value: value.endswith(needle),
    }[operator]
    expected = [value for value in values if match(value)]
    assert actual == expected
    assert count == len(expected)

