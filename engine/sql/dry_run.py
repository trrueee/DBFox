from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
) -> DryRunResult:
    """Validate approved SQL with a read-only connection-factory scope."""

    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if datasource is None:
        return DryRunResult(False, "explain_unavailable", "Datasource scope could not be resolved.")

    factory = connection_factory or ConnectionFactory()
    try:
        profile = ConnectionProfile.from_mapping(datasource_connection_dict(datasource))
        if profile.dialect == "sqlite":
            return _dry_run_sqlite(profile, sql, factory)
        if profile.dialect == "duckdb":
            return _dry_run_duckdb(profile, sql, factory)
        if profile.dialect == "postgresql":
            return _dry_run_postgres(profile, sql, factory)
        return _dry_run_mysql(profile, sql, factory)
    except Exception as exc:
        from engine.policy.error_sanitizer import sanitize_error_message

        return DryRunResult(False, _classify_dry_run_error(exc), sanitize_error_message(str(exc)))


def _dry_run_sqlite(
    profile: ConnectionProfile,
    sql: str,
    factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "sqlite")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        conn.execute(f"EXPLAIN QUERY PLAN {sql}")
    return DryRunResult(True)


def _dry_run_duckdb(
    profile: ConnectionProfile,
    sql: str,
    factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "duckdb")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        conn.execute(f"EXPLAIN {sql}")
    return DryRunResult(True)


def _dry_run_mysql(
    profile: ConnectionProfile,
    sql: str,
    factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "mysql")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}")
    return DryRunResult(True)


def _dry_run_postgres(
    profile: ConnectionProfile,
    sql: str,
    factory: ConnectionFactory,
) -> DryRunResult:
    _validate_explain_sql(sql, "postgres")
    with factory.connection_scope(
        profile,
        purpose=ConnectionPurpose.DRY_RUN,
        read_only=True,
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}")
    return DryRunResult(True)


def _classify_dry_run_error(exc: Exception) -> DryRunReason:
    message = str(exc).lower()
    if (
        "no such table" in message
        or "no such column" in message
        or "unknown table" in message
        or "unknown column" in message
        or "doesn't exist" in message
        or "does not exist" in message
    ):
        return "schema_error"
    if (
        "syntax" in message
        or "parse" in message
        or "no such function" in message
        or "near " in message
    ):
        return "syntax_error"
    return "explain_unavailable"
