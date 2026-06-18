from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

import pymysql
from sqlalchemy.orm import Session

from engine.datasource import datasource_connection_dict, get_mysql_connection_params, get_postgres_connection_params
from engine.models import DataSource


DryRunReason = Literal["syntax_error", "schema_error", "explain_unavailable"]


@dataclass(frozen=True)
class DryRunResult:
    ok: bool
    blocked_reason: DryRunReason | None = None
    message: str | None = None


from engine.sql.executor import _validate_explain_sql


def dry_run_query(db: Session, datasource_id: str, sql: str) -> DryRunResult:
    datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if datasource is None:
        return DryRunResult(False, "explain_unavailable", "Datasource scope could not be resolved.")

    db_type = str(datasource.db_type or "mysql").lower()
    try:
        if db_type == "sqlite":
            return _dry_run_sqlite(str(datasource.database_name or ""), sql)
        if "postgres" in db_type:
            return _dry_run_postgres(datasource, sql)
        return _dry_run_mysql(datasource, sql)
    except Exception as exc:
        from engine.policy.error_sanitizer import sanitize_error_message
        return DryRunResult(False, _classify_dry_run_error(exc), sanitize_error_message(str(exc)))


def _dry_run_sqlite(database_name: str, sql: str) -> DryRunResult:
    import pathlib
    _validate_explain_sql(sql, "sqlite")
    path = database_name
    db_uri = pathlib.Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True)
    try:
        conn.execute(f"EXPLAIN QUERY PLAN {sql}")
        return DryRunResult(True)
    finally:
        conn.close()


def _dry_run_mysql(datasource: DataSource, sql: str) -> DryRunResult:
    _validate_explain_sql(sql, "mysql")
    params = get_mysql_connection_params(datasource_connection_dict(datasource))
    conn = pymysql.connect(**params)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}")
        return DryRunResult(True)
    finally:
        conn.close()


def _dry_run_postgres(datasource: DataSource, sql: str) -> DryRunResult:
    _validate_explain_sql(sql, "postgres")
    import psycopg2

    params = get_postgres_connection_params(datasource_connection_dict(datasource))
    conn = psycopg2.connect(
        host=params.get("host"),
        port=params.get("port"),
        user=params.get("user"),
        password=params.get("password"),
        database=params.get("database"),
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}")
        return DryRunResult(True)
    finally:
        conn.close()


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
