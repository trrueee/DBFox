"""Restrictions specific to an immutable, single-table workbook query source."""
from __future__ import annotations

import duckdb
from sqlglot import exp

from .contracts import WorkbookDatabaseHandle
from .sql.readonly_query import parse_single_readonly_query
from .store import DataStateStore

_FUNCTIONS = frozenset({
    "SUM", "COUNT", "MAX", "MIN", "AVG", "COALESCE", "NULLIF", "CAST", "ROUND", "ABS",
    "UPPER", "LOWER", "TRIM", "DATE_TRUNC", "TIMESTAMP_TRUNC", "STRFTIME", "EXTRACT",
    "YEAR", "MONTH", "DAY", "ROW_NUMBER", "RANK", "DENSE_RANK", "IF", "CASE",
    "AND", "OR", "NOT",
    "REGEXP_EXTRACT", "REGEXP_REPLACE",
})


class WorkbookQueryError(ValueError):
    """A bounded, public-safe explanation of the workbook SQL subset."""


def validate_workbook_query(sql: str) -> None:
    expression = parse_single_readonly_query(sql, "duckdb")
    ctes = {cte.alias for cte in expression.find_all(exp.CTE)}
    tables = list(expression.find_all(exp.Table))
    if not any(t.name == "data" and isinstance(t.this, exp.Identifier) for t in tables):
        raise WorkbookQueryError("Workbook queries must read the prepared data table")
    for table in tables:
        if not isinstance(table.this, exp.Identifier) or table.catalog or table.db not in ("", "main") or table.name not in {"data", *ctes}:
            raise WorkbookQueryError("Only the prepared workbook table and local CTEs are allowed")
    for node in expression.walk():
        if isinstance(node, exp.TryCast):
            raise WorkbookQueryError("Tolerant conversion cannot bypass workbook type checks")
        if isinstance(node, exp.Func):
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            if str(name).upper() not in _FUNCTIONS:
                raise WorkbookQueryError("This function is outside the supported workbook analysis scope. "
                                         "Supported functions: " + ", ".join(sorted(_FUNCTIONS)))


def open_workbook_query(handle: WorkbookDatabaseHandle):
    DataStateStore.check_workbook_files(handle)
    return duckdb.connect(str(handle.path), read_only=True, config={
        "enable_external_access": False, "autoinstall_known_extensions": False,
        "autoload_known_extensions": False, "allow_unsigned_extensions": False,
        "threads": 1, "memory_limit": "128MB", "lock_configuration": True,
    })
