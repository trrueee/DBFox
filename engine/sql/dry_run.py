from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from sqlalchemy.orm import Session

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.datasource import datasource_connection_dict
from engine.models import DataSource
from dlcs.dbfox_data.backend.sql.dry_run_contracts import (
    DryRunResult,
    classify_dry_run_error,
)

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
        from dlcs.dbfox_data.backend.sql.bound_parameters import render_dbapi_sql
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
            classify_dry_run_error(exc, dialect),
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
