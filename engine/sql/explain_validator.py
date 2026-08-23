"""Shared EXPLAIN input validator — extracted from executor.py to break
the circular import chain executor → safety_gate → trust_gate → dry_run → executor.

Both :func:`dry_run_query` and :func:`explain_sql` need to validate EXPLAIN
inputs before constructing f-string queries.  Hosting this in a leaf module
lets both callers import it without creating a cycle.
"""

from __future__ import annotations

from engine.errors import GuardrailValidationError
from dlcs.dbfox_data.backend.sql.readonly_query import (
    ReadonlyQueryError,
    parse_single_readonly_query,
)


def validate_explain_sql(sql: str, dialect: str) -> None:
    """Secondary safety check for EXPLAIN inputs to prevent SQL injection in f-strings.

    Raises :class:`GuardrailValidationError` when the supplied SQL does not
    look like a safe, single SELECT / UNION statement suitable for wrapping in
    ``EXPLAIN ...`` format strings.
    """
    try:
        parse_single_readonly_query(sql, dialect)
    except ReadonlyQueryError as exc:
        raise GuardrailValidationError(
            "EXPLAIN requires exactly one side-effect-free query statement."
        ) from exc
