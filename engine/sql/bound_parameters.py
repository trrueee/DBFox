from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.dialects.mysql import MySQL
from sqlglot.dialects.duckdb import DuckDB

from engine.json_codec import dumps
from engine.sql.dialect_context import canonical_sql_dialect


_INTERNAL_PARAMETER = re.compile(r"^dbfox_p\d+$")


class _MySQLBoundGenerator(MySQL.Generator):
    def placeholder_sql(self, expression: exp.Placeholder) -> str:
        name = expression.name
        return f"%({name})s" if name else "%s"


class _DuckDBBoundGenerator(DuckDB.Generator):
    def placeholder_sql(self, expression: exp.Placeholder) -> str:
        name = expression.name
        return f"${name}" if name else "?"


def parameter_fingerprint(parameters: Mapping[str, Any] | None) -> str | None:
    if not parameters:
        return None
    canonical = dumps(dict(sorted((parameters or {}).items())))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_dbapi_sql(
    sql: str,
    dialect: str,
    parameters: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Render canonical named placeholders to the target DB-API paramstyle."""
    bound = dict(parameters or {})
    expression = sqlglot.parse_one(sql, read=_sqlglot_dialect(dialect))
    names = [node.name for node in expression.find_all(exp.Placeholder) if node.name]
    if any(not _INTERNAL_PARAMETER.fullmatch(name) for name in names):
        raise ValueError("Only DBFox internal named parameters are allowed.")
    if set(names) != set(bound):
        raise ValueError("SQL placeholders and bound parameters do not match.")
    if not names:
        if bound:
            raise ValueError("Bound parameters were supplied for SQL without placeholders.")
        return sql, {}

    canonical = "duckdb" if dialect.strip().lower() == "duckdb" else canonical_sql_dialect(dialect)
    if canonical == "mysql":
        rendered = _MySQLBoundGenerator().generate(expression)
    elif canonical == "duckdb":
        rendered = _DuckDBBoundGenerator().generate(expression)
    else:
        target = "postgres" if canonical == "postgresql" else canonical
        rendered = expression.sql(dialect=target)
    return rendered, bound


def _sqlglot_dialect(dialect: str) -> str:
    canonical = "duckdb" if dialect.strip().lower() == "duckdb" else canonical_sql_dialect(dialect)
    return "postgres" if canonical == "postgresql" else canonical
