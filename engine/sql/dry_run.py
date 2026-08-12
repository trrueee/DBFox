from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from collections.abc import Mapping

from sqlalchemy.orm import Session

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.datasource import datasource_connection_dict
from engine.models import DataSource


DryRunReason = Literal["syntax_error", "schema_error", "explain_unavailable"]


@dataclass(frozen=True)
class DryRunResult:
    ok: bool
    blocked_reason: DryRunReason | None = None
    message: str | None = None


from engine.sql.explain_validator import validate_explain_sql as _validate_explain_sql


def dry_run_query(
    db: Session,
    datasource_id: str,
    sql: str,
    *,
    connection_factory: ConnectionFactory | None = None,
    parameters: Mapping[str, Any] | None = None,
) -> DryRunResult:
    """Validate approved SQL with a read-only connection-factory scope."""

    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if datasource is None:
        return DryRunResult(False, "explain_unavailable", "Datasource scope could not be resolved.")

    factory = connection_factory or ConnectionFactory()
    dialect = "unknown"
    try:
        profile = ConnectionProfile.from_mapping(datasource_connection_dict(datasource))
        dialect = profile.dialect
        from engine.sql.bound_parameters import render_dbapi_sql
        executable_sql, bound = render_dbapi_sql(sql, profile.dialect, parameters)
        if profile.dialect == "sqlite":
            return _dry_run_sqlite(profile, executable_sql, bound, factory)
        if profile.dialect == "duckdb":
            return _dry_run_duckdb(profile, executable_sql, bound, factory)
        if profile.dialect == "postgresql":
            return _dry_run_postgres(profile, executable_sql, bound, factory)
        return _dry_run_mysql(profile, executable_sql, bound, factory)
    except Exception as exc:
        from engine.policy.error_sanitizer import sanitize_error_message

        return DryRunResult(
            False,
            _classify_dry_run_error(exc, dialect),
            sanitize_error_message(str(exc)),
        )


def _dry_run_sqlite(
    profile: ConnectionProfile,
    sql: str,
    parameters: Mapping[str, Any], factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "sqlite")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        conn.execute(f"EXPLAIN QUERY PLAN {sql}", parameters)
    return DryRunResult(True)


def _dry_run_duckdb(
    profile: ConnectionProfile,
    sql: str,
    parameters: Mapping[str, Any], factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "duckdb")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        conn.execute(f"EXPLAIN {sql}", parameters)
    return DryRunResult(True)


def _dry_run_mysql(
    profile: ConnectionProfile,
    sql: str,
    parameters: Mapping[str, Any], factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "mysql")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}", parameters)
    return DryRunResult(True)


def _dry_run_postgres(
    profile: ConnectionProfile,
    sql: str,
    parameters: Mapping[str, Any], factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "postgres")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}", parameters)
    return DryRunResult(True)


def _classify_dry_run_error(exc: Exception, dialect: str) -> DryRunReason:
    """Classify EXPLAIN failures using each driver's stable error contract.

    PostgreSQL exposes SQLSTATE, MySQL exposes numeric server codes, and
    DuckDB exposes typed exception classes. SQLite does not provide a granular
    SQLSTATE equivalent, so its own documented error text remains the final,
    dialect-local discriminator rather than a cross-provider string mapper.
    """

    if dialect == "postgresql":
        sqlstate = str(
            getattr(exc, "pgcode", None)
            or getattr(getattr(exc, "diag", None), "sqlstate", None)
            or ""
        )
        if sqlstate in {"42P01", "42703"}:  # undefined table / column
            return "schema_error"
        if sqlstate in {"42601", "42883"}:  # syntax / undefined function
            return "syntax_error"

    if dialect == "mysql":
        error_code = exc.args[0] if exc.args else None
        if error_code in {1054, 1109, 1146}:  # column / table resolution
            return "schema_error"
        if error_code in {1064, 1305}:  # syntax / function resolution
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
