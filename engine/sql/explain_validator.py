"""Shared EXPLAIN input validator — extracted from executor.py to break
the circular import chain executor → safety_gate → trust_gate → dry_run → executor.

Both :func:`dry_run_query` and :func:`explain_sql` need to validate EXPLAIN
inputs before constructing f-string queries.  Hosting this in a leaf module
lets both callers import it without creating a cycle.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from engine.errors import GuardrailValidationError
from engine.sql.parser import normalize_dialect


def validate_explain_sql(sql: str, dialect: str) -> None:
    """Secondary safety check for EXPLAIN inputs to prevent SQL injection in f-strings.

    Raises :class:`GuardrailValidationError` when the supplied SQL does not
    look like a safe, single SELECT / UNION statement suitable for wrapping in
    ``EXPLAIN ...`` format strings.
    """
    sql_stripped = sql.strip()
    while sql_stripped.endswith(";"):
        sql_stripped = sql_stripped[:-1].strip()

    sqlglot_dialect = normalize_dialect(dialect)

    try:
        exprs = sqlglot.parse(sql_stripped, read=sqlglot_dialect)
    except Exception as exc:
        raise GuardrailValidationError(f"SQL syntax error in EXPLAIN query: {exc}")

    if len(exprs) != 1 or not exprs[0]:
        raise GuardrailValidationError("EXPLAIN query must contain exactly one SQL statement.")

    expr = exprs[0]
    if not isinstance(expr, (exp.Select, exp.Union)):
        raise GuardrailValidationError("EXPLAIN query must be a SELECT or UNION statement.")

    for node in expr.walk():
        if isinstance(node, (exp.Command, exp.Execute)):
            raise GuardrailValidationError("EXPLAIN query contains blocked command types.")
