"""Canonical SQLGlot contract for one side-effect-free query statement."""

from __future__ import annotations

from enum import StrEnum
from typing import cast

from sqlglot import exp

from engine.sql.parser import parse_sql


class ReadonlyQueryErrorReason(StrEnum):
    EMPTY = "empty"
    PARSE_ERROR = "parse_error"
    MULTIPLE_STATEMENTS = "multiple_statements"
    NOT_READONLY = "not_readonly"


class ReadonlyQueryError(ValueError):
    def __init__(self, reason: ReadonlyQueryErrorReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


READONLY_FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Merge,
    exp.Execute,
    exp.TruncateTable,
    exp.LoadData,
    exp.Copy,
    exp.Into,
    exp.Lock,
)


# These functions are syntactically valid in a query but mutate persistent or
# session state.  Keep the list at the canonical read-only boundary so every
# consumer (Guardrail, EXPLAIN, safety validation, and SQL-backed views) makes
# the same decision.
READONLY_SIDE_EFFECT_FUNCTIONS_BY_DIALECT = {
    "postgres": frozenset({
        # Sequence state. nextval/setval changes are not rolled back.
        "nextval",
        "setval",
        # Session/transaction advisory-lock state.
        "pg_advisory_lock",
        "pg_advisory_lock_shared",
        "pg_advisory_xact_lock",
        "pg_advisory_xact_lock_shared",
        "pg_try_advisory_lock",
        "pg_try_advisory_lock_shared",
        "pg_try_advisory_xact_lock",
        "pg_try_advisory_xact_lock_shared",
        "pg_advisory_unlock",
        "pg_advisory_unlock_shared",
        "pg_advisory_unlock_all",
        # Server control, server-file access and extension-backed remote writes.
        "pg_read_binary_file",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "dblink_exec",
    }),
    "mysql": frozenset({
        # MySQL user-level lock state.
        "get_lock",
        "release_lock",
        "release_all_locks",
    }),
}

_ALL_READONLY_SIDE_EFFECT_FUNCTIONS = frozenset().union(
    *READONLY_SIDE_EFFECT_FUNCTIONS_BY_DIALECT.values()
)


def readonly_side_effect_functions(dialect: str | None) -> frozenset[str]:
    normalized = str(dialect or "").strip().lower()
    if normalized == "postgresql":
        normalized = "postgres"
    if not normalized:
        return _ALL_READONLY_SIDE_EFFECT_FUNCTIONS
    return READONLY_SIDE_EFFECT_FUNCTIONS_BY_DIALECT.get(normalized, frozenset())


def _function_name(node: exp.Expression) -> str:
    if not isinstance(node, (exp.Anonymous, exp.Func)):
        return ""
    return str(node.name or "").strip().lower()


def is_readonly_query(node: exp.Expression, dialect: str | None = None) -> bool:
    """Return whether the complete AST is a side-effect-free query."""

    if not isinstance(node, exp.Query):
        return False
    for descendant in node.walk():
        if isinstance(descendant, READONLY_FORBIDDEN_TYPES):
            return False
        if _function_name(descendant) in readonly_side_effect_functions(dialect):
            return False
    return True


def parse_single_readonly_query(sql: str, dialect: str) -> exp.Query:
    """Parse exactly one SQLGlot Query and reject nested side effects."""

    if not str(sql or "").strip():
        raise ReadonlyQueryError(
            ReadonlyQueryErrorReason.EMPTY,
            "SQL query is empty.",
        )
    try:
        expressions = parse_sql(sql, dialect)
    except Exception as exc:
        raise ReadonlyQueryError(
            ReadonlyQueryErrorReason.PARSE_ERROR,
            "SQL query could not be parsed.",
        ) from exc
    if len(expressions) != 1 or expressions[0] is None:
        raise ReadonlyQueryError(
            ReadonlyQueryErrorReason.MULTIPLE_STATEMENTS,
            "SQL query must contain exactly one statement.",
        )
    expression = expressions[0]
    if not is_readonly_query(expression, dialect):
        raise ReadonlyQueryError(
            ReadonlyQueryErrorReason.NOT_READONLY,
            "SQL query must be a side-effect-free query statement.",
        )
    return cast(exp.Query, expression)
