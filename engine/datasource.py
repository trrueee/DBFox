"""Compatibility entry points backed by the typed connectivity boundary."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.connectivity.factory import (
    ConnectionFactory,
    build_mysql_ssl_params,
    build_postgres_ssl_params,
)
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import get_credential_vault
from engine.sql.permissions import MySQLPermissionProbe, PostgresPermissionProbe, SQLitePermissionProbe
from engine.tunnel import (
    TUNNEL_MANAGER,
    close_active_tunnel,
    close_all_tunnels,
    get_or_create_tunnel_for_dict,
    open_temporary_tunnel,
)


logger = logging.getLogger("dbfox.datasource")


def _profile(
    config: Mapping[str, Any] | ConnectionProfile,
    *,
    expected_dialect: str | None = None,
) -> ConnectionProfile:
    if isinstance(config, ConnectionProfile):
        profile = config
    else:
        normalized = dict(config)
        if expected_dialect and not normalized.get("db_type"):
            normalized["db_type"] = expected_dialect
        profile = ConnectionProfile.from_mapping(normalized)
    if expected_dialect and profile.dialect != expected_dialect:
        raise DataSourceConnectionError("Connection profile dialect does not match the requested driver.")
    return profile


def _factory() -> ConnectionFactory:
    """Resolve the vault only at the runtime connection boundary."""
    return ConnectionFactory(vault=get_credential_vault())


def _test_purpose(profile: ConnectionProfile) -> ConnectionPurpose:
    return ConnectionPurpose.HEALTH_CHECK if profile.is_managed else ConnectionPurpose.CONNECTION_TEST


def _first_row_value(row: Any) -> Any | None:
    """Return the first selected value for tuple- and dict-based cursors."""
    if not row:
        return None
    if isinstance(row, Mapping):
        return next(iter(row.values()), None)
    return row[0]


def _log_connection_failure(operation: SafeLogOperation, exc: DataSourceConnectionError) -> None:
    """Record only the driver exception class when a boundary wrapped it.

    ``ConnectionFactory`` deliberately replaces driver messages with a stable
    public error.  Preserve a useful diagnostic signal here without ever
    logging the wrapped message, which can contain a DSN or password.
    Expected validation failures have no cause and are intentionally silent.
    """

    cause = exc.__cause__
    if isinstance(cause, Exception):
        log_unexpected_exception(
            logger,
            operation=operation,
            exc=cause,
            level="warning",
        )


def test_connection(config: Mapping[str, Any] | ConnectionProfile) -> dict[str, Any]:
    """Test connectivity without ever accepting plaintext credentials in config."""
    profile = _profile(config)
    factory = _factory()
    if profile.dialect == "sqlite":
        return _test_sqlite_connection(profile, factory)
    if profile.dialect == "duckdb":
        return _test_duckdb_connection(profile, factory)
    if profile.dialect == "postgresql":
        return _test_postgres_connection(profile, factory)
    return _test_mysql_connection(profile, factory)


def _test_sqlite_connection(profile: ConnectionProfile, factory: ConnectionFactory) -> dict[str, Any]:
    try:
        with factory.connection_scope(
            profile,
            purpose=_test_purpose(profile),
            read_only=True,
            pooled=False,
        ) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version_row = cursor.fetchone()
            version = str(version_row[0]) if version_row else "unknown"

            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            tables_row = cursor.fetchone()
            tables_count = int(tables_row[0]) if tables_row else 0

            permission_report = SQLitePermissionProbe(
                database_path=factory.sqlite_path(profile),
                connection_readonly=True,
            ).probe(conn)
            return {
                "ok": True,
                "serverVersion": f"SQLite {version}",
                "readonly": permission_report.readonly,
                "tablesCount": tables_count,
                "warnings": permission_report.warnings,
                "permissionReport": permission_report.model_dump(),
                "message": "SQLite 数据库连接测试成功！",
            }
    except DataSourceConnectionError as exc:
        _log_connection_failure(SafeLogOperation.DATASOURCE_TEST_SQLITE_CONNECTION, exc)
        raise
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.DATASOURCE_TEST_SQLITE_CONNECTION,
            exc=exc,
            level="warning",
        )
        raise DataSourceConnectionError("无法建立 SQLite 数据库连接，请检查路径配置。") from None


def _test_duckdb_connection(profile: ConnectionProfile, factory: ConnectionFactory) -> dict[str, Any]:
    try:
        with factory.connection_scope(
            profile,
            purpose=_test_purpose(profile),
            read_only=True,
            pooled=False,
        ) as conn:
            version_row = conn.execute("SELECT version()").fetchone()
            version = str(version_row[0]) if version_row else "unknown"
            tables_row = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')"
            ).fetchone()
            tables_count = int(tables_row[0]) if tables_row else 0
            return {
                "ok": True,
                "serverVersion": f"DuckDB {version}",
                "readonly": True,
                "tablesCount": tables_count,
                "warnings": [],
                "permissionReport": {
                    "readonly": True,
                    "writable_privileges": [],
                    "warnings": [],
                    "evidence": {"probe": "duckdb_read_only_connection"},
                },
                "message": "DuckDB 数据库连接测试成功！",
            }
    except DataSourceConnectionError as exc:
        _log_connection_failure(SafeLogOperation.DATASOURCE_TEST_DUCKDB_CONNECTION, exc)
        raise
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.DATASOURCE_TEST_DUCKDB_CONNECTION,
            exc=exc,
            level="warning",
        )
        raise DataSourceConnectionError("无法建立 DuckDB 数据库连接，请检查路径配置。") from None


def _test_postgres_connection(profile: ConnectionProfile, factory: ConnectionFactory) -> dict[str, Any]:
    try:
        with factory.connection_scope(
            profile,
            purpose=_test_purpose(profile),
            read_only=True,
            pooled=False,
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT version()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    """
                )
                tables_row = cursor.fetchone()
                tables_count = int(tables_row[0]) if tables_row else 0

            permission_report = PostgresPermissionProbe().probe(conn)
            return {
                "ok": True,
                "serverVersion": version,
                "readonly": permission_report.readonly,
                "tablesCount": tables_count,
                "warnings": permission_report.warnings,
                "permissionReport": permission_report.model_dump(),
                "message": "PostgreSQL 数据库连接测试成功！",
            }
    except DataSourceConnectionError as exc:
        _log_connection_failure(SafeLogOperation.DATASOURCE_TEST_POSTGRES_CONNECTION, exc)
        raise
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.DATASOURCE_TEST_POSTGRES_CONNECTION,
            exc=exc,
            level="warning",
        )
        raise DataSourceConnectionError("无法建立 PostgreSQL 数据库连接，请检查配置信息。") from None


def _test_mysql_connection(profile: ConnectionProfile, factory: ConnectionFactory) -> dict[str, Any]:
    try:
        with factory.connection_scope(
            profile,
            purpose=_test_purpose(profile),
            read_only=True,
            pooled=False,
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                version_row = cursor.fetchone()
                version_value = _first_row_value(version_row)
                version = str(version_value) if version_value is not None else "unknown"

                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                    (profile.database_name,),
                )
                tables_row = cursor.fetchone()
                tables_value = _first_row_value(tables_row)
                tables_count = int(tables_value) if tables_value is not None else 0

            permission_report = MySQLPermissionProbe().probe(conn)
            return {
                "ok": True,
                "serverVersion": version,
                "readonly": permission_report.readonly,
                "tablesCount": tables_count,
                "warnings": permission_report.warnings,
                "permissionReport": permission_report.model_dump(),
                "message": "数据库连接测试成功！",
            }
    except DataSourceConnectionError as exc:
        _log_connection_failure(SafeLogOperation.DATASOURCE_TEST_MYSQL_CONNECTION, exc)
        raise
    except Exception as exc:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.DATASOURCE_TEST_MYSQL_CONNECTION,
            exc=exc,
            level="warning",
        )
        raise DataSourceConnectionError("无法建立 MySQL 数据库连接，请检查主机、端口、用户名和 SSL 配置。") from None


def datasource_connection_dict(ds: Any) -> dict[str, Any]:
    """Extract opaque connection metadata from a persisted datasource row."""
    return {
        "id": ds.id,
        "is_managed": True,
        "db_type": ds.db_type or "mysql",
        "host": ds.host,
        "port": ds.port,
        "username": ds.username,
        "database_name": ds.database_name,
        "password_credential_id": ds.password_credential_id,
        # Do not normalize a corrupted or missing persisted generation to one:
        # ``ConnectionProfile`` is the validation boundary that must reject it
        # rather than potentially colliding with an existing resource key.
        "connection_generation": ds.connection_generation,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_credential_id": ds.ssh_password_credential_id,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_key_passphrase_credential_id": ds.ssh_key_passphrase_credential_id,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    }
