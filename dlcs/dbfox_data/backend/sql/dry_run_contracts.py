"""Pure EXPLAIN validation contracts owned by the Data capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DryRunReason = Literal["syntax_error", "schema_error", "explain_unavailable"]


@dataclass(frozen=True)
class DryRunResult:
    ok: bool
    blocked_reason: DryRunReason | None = None
    message: str | None = None


def classify_dry_run_error(exc: Exception, dialect: str) -> DryRunReason:
    """Classify EXPLAIN failures using each driver's stable error contract."""

    if dialect == "postgresql":
        sqlstate = str(
            getattr(exc, "pgcode", None)
            or getattr(getattr(exc, "diag", None), "sqlstate", None)
            or ""
        )
        if sqlstate in {"42P01", "42703"}:
            return "schema_error"
        if sqlstate in {"42601", "42883"}:
            return "syntax_error"

    if dialect == "mysql":
        error_code = exc.args[0] if exc.args else None
        if error_code in {1054, 1109, 1146}:
            return "schema_error"
        if error_code in {1064, 1305}:
            return "syntax_error"

    if dialect == "duckdb":
        exception_name = type(exc).__name__
        if exception_name in {"BinderException", "CatalogException"}:
            return "schema_error"
        if exception_name in {"ParserException", "SyntaxException"}:
            return "syntax_error"

    if dialect == "sqlite":
        message = str(exc).lower()
        if "no such table" in message or "no such column" in message:
            return "schema_error"
        if "syntax error" in message or "no such function" in message or "near " in message:
            return "syntax_error"

    return "explain_unavailable"
