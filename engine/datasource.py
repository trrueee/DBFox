from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pymysql

from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialKind, get_credential_vault
from engine.sql.permissions import MySQLPermissionProbe, PostgresPermissionProbe, SQLitePermissionProbe
from engine.tunnel import (
    TUNNEL_MANAGER,
    close_active_tunnel,
    close_all_tunnels,
    get_or_create_tunnel_for_dict,
    open_temporary_tunnel,
)

logger = logging.getLogger("dbfox.datasource")


def _resolve_credential_secret(
    datasource_dict: dict[str, Any],
    field: str,
    kind: CredentialKind,
) -> str:
    credential_id = datasource_dict.get(field)
    if not credential_id:
        return ""
    secret = get_credential_vault().get(str(credential_id), expected_kind=kind)
    if secret is None:
        raise DataSourceConnectionError("Credential reference was not found or has the wrong kind.")
    return secret


def _normalized_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_existing_sqlite_file(db_path: Any) -> Path:
    path_text = str(db_path or "").strip()
    if not path_text:
        raise DataSourceConnectionError("未提供 SQLite 数据库文件路径。")
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise DataSourceConnectionError(f"SQLite 数据库文件不存在: {path}")
    return path


def build_mysql_ssl_params(config: dict[str, Any]) -> dict[str, Any]:
    """Build PyMySQL SSL parameters with certificate verification enabled."""
    if not config.get("ssl_enabled"):
        return {}

    ca_path = _normalized_optional_path(config.get("ssl_ca_path"))
    cert_path = _normalized_optional_path(config.get("ssl_cert_path"))
    key_path = _normalized_optional_path(config.get("ssl_key_path"))
    verify_identity = bool(config.get("ssl_verify_identity", True))

    if verify_identity and not ca_path:
        raise DataSourceConnectionError("SSL identity verification requires a CA certificate path.")

    ssl_params: dict[str, Any] = {
        "ssl_verify_cert": True,
        "ssl_verify_identity": verify_identity,
    }
    if ca_path:
        ssl_params["ssl_ca"] = ca_path
    if cert_path:
        ssl_params["ssl_cert"] = cert_path
    if key_path:
        ssl_params["ssl_key"] = key_path
    return ssl_params


def build_postgres_ssl_params(config: dict[str, Any]) -> dict[str, Any]:
    """Build psycopg2 SSL parameters from the shared datasource SSL fields."""
    if not config.get("ssl_enabled"):
        return {}

    ca_path = _normalized_optional_path(config.get("ssl_ca_path"))
    cert_path = _normalized_optional_path(config.get("ssl_cert_path"))
    key_path = _normalized_optional_path(config.get("ssl_key_path"))
    verify_identity = bool(config.get("ssl_verify_identity", True))

    if verify_identity and not ca_path:
        raise DataSourceConnectionError("PostgreSQL SSL identity verification requires a CA certificate path.")

    params: dict[str, Any] = {
        "sslmode": "verify-full" if verify_identity else ("verify-ca" if ca_path else "require"),
    }
    if ca_path:
        params["sslrootcert"] = ca_path
    if cert_path:
        params["sslcert"] = cert_path
    if key_path:
        params["sslkey"] = key_path
    return params


def get_mysql_connection_params(datasource_dict: dict[str, Any]) -> dict[str, Any]:
    """Resolve an OS-vault password and construct PyMySQL parameters."""
    pw = _resolve_credential_secret(
        datasource_dict,
        "password_credential_id",
        CredentialKind.DATASOURCE_PASSWORD,
    )
    host = datasource_dict["host"]
    port = datasource_dict["port"]

    if datasource_dict.get("ssh_enabled"):
        tunnel = get_or_create_tunnel_for_dict(datasource_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    params = {
        "host": host,
        "port": port,
        "user": datasource_dict["username"],
        "password": pw,
        "database": datasource_dict["database_name"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
    }
    params.update(build_mysql_ssl_params(datasource_dict))
    return params


def get_postgres_connection_params(datasource_dict: dict[str, Any]) -> dict[str, Any]:
    """Resolve an OS-vault password and construct PostgreSQL parameters."""
    pw = _resolve_credential_secret(
        datasource_dict,
        "password_credential_id",
        CredentialKind.DATASOURCE_PASSWORD,
    )
    host = datasource_dict["host"]
    port = int(datasource_dict.get("port", 5432) or 5432)

    if datasource_dict.get("ssh_enabled"):
        tunnel = get_or_create_tunnel_for_dict(datasource_dict)
        host = "127.0.0.1"
        port = tunnel.local_bind_port

    params = {
        "host": host,
        "port": port,
        "user": datasource_dict["username"],
        "password": pw,
        "database": datasource_dict["database_name"],
    }
    params.update(build_postgres_ssl_params(datasource_dict))
    return params


def _setup_test_tunnel(config: dict[str, Any]) -> tuple[str, int, Any | None]:
    """Resolve SSH tunnel for a connection test. Returns (host, port, tunnel).

    When SSH is enabled, the returned host/port point to the local tunnel
    endpoint.  When SSH is disabled or not configured, the original host/port
    are returned unchanged and *tunnel* is ``None``.
    """
    if not config.get("ssh_enabled"):
        return config.get("host", ""), config.get("port", 3306), None

    try:
        if config.get("is_managed"):
            tunnel = get_or_create_tunnel_for_dict(config)
        else:
            tunnel = open_temporary_tunnel(config)
        return "127.0.0.1", tunnel.local_bind_port, tunnel
    except Exception as e:
        raise DataSourceConnectionError(f"无法建立 SSH 隧道，请检查跳板机配置。错误: {str(e)}")


def _cleanup_test_tunnel(tunnel: Any | None, config: dict[str, Any]) -> None:
    """Stop a temporary test tunnel unless it is managed."""
    if tunnel is not None and not config.get("is_managed"):
        try:
            tunnel.stop()
        except Exception as e:
            logger.warning(
                "Failed to stop test tunnel (host=%s port=%s): %s",
                config.get("ssh_host", "unknown"),
                config.get("ssh_port", "unknown"),
                e,
            )


def test_connection(config: dict[str, Any]) -> dict[str, Any]:
    """Test connectivity to a database — dispatches to the dialect-specific strategy."""
    db_type = config.get("db_type", "mysql")

    if db_type == "sqlite":
        return _test_sqlite_connection(config)
    if db_type == "postgresql":
        return _test_postgres_connection(config)
    return _test_mysql_connection(config)


# ── Dialect-specific connection testers ──────────────────────────────────────────


def _test_sqlite_connection(config: dict[str, Any]) -> dict[str, Any]:
    import sqlite3

    db_path = _require_existing_sqlite_file(config.get("database_name", ""))
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", timeout=5, uri=True)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version()")
            version_row = cursor.fetchone()
            version = str(version_row[0]) if version_row else "unknown"

            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            tables_row = cursor.fetchone()
            tables_count = int(tables_row[0]) if tables_row else 0

            permission_report = SQLitePermissionProbe(
                database_path=db_path,
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
        finally:
            conn.close()
    except DataSourceConnectionError:
        raise
    except Exception as e:
        raise DataSourceConnectionError(f"无法建立 SQLite 数据库连接，请检查路径配置。错误: {str(e)}")


def _test_postgres_connection(config: dict[str, Any]) -> dict[str, Any]:
    import psycopg2

    host = config.get("host", "")
    port = config.get("port", 5432)
    database_name = config.get("database_name", "")
    username = config.get("username", "")
    password = config.get("password", "")

    if not host or not database_name or not username:
        raise DataSourceConnectionError("Missing host, database name, or username configuration.")

    temp_tunnel = None
    try:
        test_host, test_port, temp_tunnel = _setup_test_tunnel(config)
        conn = psycopg2.connect(
            host=test_host, port=test_port, user=username, password=password,
            database=database_name, connect_timeout=5,
            **build_postgres_ssl_params(config),
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT version()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                """)
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
        finally:
            conn.close()
    except DataSourceConnectionError:
        raise
    except Exception as e:
        raise DataSourceConnectionError(f"无法建立 PostgreSQL 数据库连接，请检查配置信息。错误详情: {str(e)}")
    finally:
        _cleanup_test_tunnel(temp_tunnel, config)


def _test_mysql_connection(config: dict[str, Any]) -> dict[str, Any]:
    host = config.get("host", "")
    port = config.get("port", 3306)
    database_name = config.get("database_name", "")
    username = config.get("username", "")
    password = config.get("password", "")

    if not host or not database_name or not username:
        raise DataSourceConnectionError("Missing host, database name, or username configuration.")

    temp_tunnel = None
    try:
        test_host, test_port, temp_tunnel = _setup_test_tunnel(config)
        conn = pymysql.connect(
            host=test_host, port=test_port, user=username, password=password,
            database=database_name, charset="utf8mb4", connect_timeout=5,
            **build_mysql_ssl_params(config),
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                    (database_name,),
                )
                tables_row = cursor.fetchone()
                tables_count = int(tables_row[0]) if tables_row else 0

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
        finally:
            conn.close()
    except DataSourceConnectionError:
        raise
    except Exception as e:
        raise DataSourceConnectionError(f"无法建立 MySQL 数据库连接，请检查主机/端口/用户名/SSL 配置。错误详情: {str(e)}")
    finally:
        _cleanup_test_tunnel(temp_tunnel, config)


def datasource_connection_dict(ds: Any) -> dict[str, Any]:
    """Build a plain dict from a DataSource row for connection helpers.

    Shared by schema sync, PostgreSQL EXPLAIN, and other paths that need the
    full datasource metadata (including SSL fields) as a dict.
    """
    return {
        "id": ds.id,
        "host": ds.host,
        "port": ds.port,
        "username": ds.username,
        "database_name": ds.database_name,
        "password_credential_id": ds.password_credential_id,
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
