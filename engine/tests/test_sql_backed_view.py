import pytest

from engine.sql.sql_backed_view import (
    SqlBackedFilter,
    SqlBackedSort,
    SqlBackedViewError,
    build_sql_backed_page_sql,
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
    assert "`name` LIKE '%acme%'" in sql
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

