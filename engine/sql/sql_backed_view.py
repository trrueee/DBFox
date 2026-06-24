from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import sqlglot
from pydantic import BaseModel
from sqlglot import exp


FilterOperator = Literal[
    "equals",
    "not_equals",
    "contains",
    "starts_with",
    "ends_with",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_null",
    "is_not_null",
    "in",
    "not_in",
]


class SqlBackedViewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class SqlBackedFilter(BaseModel):
    column: str
    operator: str
    value: Any = None


class SqlBackedSort(BaseModel):
    column: str
    direction: Literal["asc", "desc"]


@dataclass(frozen=True)
class SqlBackedQuery:
    sql: str


ALLOWED_FILTER_OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "starts_with",
    "ends_with",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_null",
    "is_not_null",
    "in",
    "not_in",
}


def build_sql_backed_page_sql(
    *,
    base_sql: str,
    dialect: str,
    columns: list[str],
    filters: list[SqlBackedFilter] | None = None,
    search: str | None = None,
    searchable_columns: list[str] | None = None,
    sorts: list[SqlBackedSort] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> SqlBackedQuery:
    """Build a safe derived SELECT over a validated SQL-backed source."""
    allowed_columns = {_normalize_column(column) for column in columns}
    base_expr = _parse_select(base_sql, dialect)

    query = sqlglot.select("*").from_(base_expr.subquery("dbfox_result"))

    for filter_item in filters or []:
        _ensure_column_allowed(filter_item.column, allowed_columns, "FILTER_COLUMN_NOT_ALLOWED")
        _ensure_operator_allowed(filter_item.operator)
        query = query.where(_filter_expression(filter_item))

    search_expr = _search_expression(
        search=search,
        searchable_columns=searchable_columns or columns,
        allowed_columns=allowed_columns,
    )
    if search_expr is not None:
        query = query.where(search_expr)

    for sort_item in sorts or []:
        _ensure_column_allowed(sort_item.column, allowed_columns, "SORT_COLUMN_NOT_ALLOWED")
        query = query.order_by(exp.Ordered(this=_column(sort_item.column), desc=sort_item.direction == "desc"))

    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    return SqlBackedQuery(sql=query.sql(dialect=dialect))


def _parse_select(base_sql: str, dialect: str) -> exp.Select:
    try:
        expressions = sqlglot.parse(base_sql, read=dialect)
    except Exception as exc:
        raise SqlBackedViewError("SOURCE_SQL_VALIDATION_FAILED", f"Source SQL parse failed: {exc}") from exc
    if len(expressions) != 1 or not isinstance(expressions[0], exp.Select):
        raise SqlBackedViewError("SOURCE_SQL_VALIDATION_FAILED", "Source SQL must be a single SELECT statement.")
    return expressions[0]


def _normalize_column(column: str) -> str:
    return column.strip().strip("`\"[]").lower()


def _ensure_column_allowed(column: str, allowed_columns: set[str], code: str) -> None:
    if _normalize_column(column) not in allowed_columns:
        raise SqlBackedViewError(code, f"Column '{column}' is not present in the source result.")


def _ensure_operator_allowed(operator: str) -> None:
    if operator not in ALLOWED_FILTER_OPERATORS:
        raise SqlBackedViewError("FILTER_OPERATOR_NOT_ALLOWED", f"Operator '{operator}' is not allowed.")


def _column(column: str) -> exp.Column:
    return exp.column(column.strip(), quoted=True)


def _literal(value: Any) -> exp.Expression:
    if value is None:
        return exp.Null()
    if isinstance(value, bool):
        return exp.Boolean(this=value)
    if isinstance(value, (int, float)):
        return exp.Literal.number(value)
    return exp.Literal.string(str(value))


def _filter_expression(item: SqlBackedFilter) -> exp.Expression:
    left = _column(item.column)
    operator = item.operator
    if operator == "equals":
        return exp.EQ(this=left, expression=_literal(item.value))
    if operator == "not_equals":
        return exp.NEQ(this=left, expression=_literal(item.value))
    if operator == "gt":
        return exp.GT(this=left, expression=_literal(item.value))
    if operator == "gte":
        return exp.GTE(this=left, expression=_literal(item.value))
    if operator == "lt":
        return exp.LT(this=left, expression=_literal(item.value))
    if operator == "lte":
        return exp.LTE(this=left, expression=_literal(item.value))
    if operator == "is_null":
        return exp.Is(this=left, expression=exp.Null())
    if operator == "is_not_null":
        return exp.Not(this=exp.Is(this=left, expression=exp.Null()))
    if operator == "contains":
        return exp.Like(this=left, expression=exp.Literal.string(f"%{item.value}%"))
    if operator == "starts_with":
        return exp.Like(this=left, expression=exp.Literal.string(f"{item.value}%"))
    if operator == "ends_with":
        return exp.Like(this=left, expression=exp.Literal.string(f"%{item.value}"))
    if operator in {"in", "not_in"}:
        raw_values = item.value if isinstance(item.value, list) else [item.value]
        expression = exp.In(this=left, expressions=[_literal(value) for value in raw_values])
        return exp.Not(this=expression) if operator == "not_in" else expression
    raise SqlBackedViewError("FILTER_OPERATOR_NOT_ALLOWED", f"Operator '{operator}' is not allowed.")


def _search_expression(
    *,
    search: str | None,
    searchable_columns: list[str],
    allowed_columns: set[str],
) -> exp.Expression | None:
    normalized_search = (search or "").strip()
    if not normalized_search:
        return None

    expressions: list[exp.Expression] = []
    for column in searchable_columns:
        _ensure_column_allowed(column, allowed_columns, "FILTER_COLUMN_NOT_ALLOWED")
        expressions.append(exp.Like(this=_column(column), expression=exp.Literal.string(f"%{normalized_search}%")))
    if not expressions:
        return None

    combined = expressions[0]
    for expression in expressions[1:]:
        combined = cast(exp.Expression, exp.or_(combined, expression))
    return combined

