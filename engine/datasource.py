from pathlib import Path
from typing import Any

import logging
import socket
import threading

import pymysql
from sshtunnel import SSHTunnelForwarder

from engine.crypto import decrypt_password
from engine.errors import DataSourceConnectionError

logger = logging.getLogger("dbfox.tunnel")


class TunnelState:
    CONNECTED = "connected"
    STALE = "stale"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSED = "closed"


class TunnelInstance:
    datasource_id: str
    ds_dict: dict[str, Any]
    tunnel: SSHTunnelForwarder
    state: str
    error_message: str | None

    def __init__(self, datasource_id: str, ds_dict: dict[str, Any], tunnel: SSHTunnelForwarder) -> None:
        self.datasource_id = datasource_id
        self.ds_dict = ds_dict
        self.tunnel = tunnel
        self.state = TunnelState.CONNECTED
        self.error_message = None


def _create_physical_tunnel_forwarder(config: dict[str, Any], is_managed: bool) -> SSHTunnelForwarder:
    ssh_password = None
    pkey_passphrase = None

    if is_managed:
        if config.get("ssh_password_ciphertext") and config.get("ssh_password_nonce"):
            ssh_password = decrypt_password(config["ssh_password_ciphertext"], config["ssh_password_nonce"])
        if config.get("ssh_pkey_passphrase_ciphertext") and config.get("ssh_pkey_passphrase_nonce"):
            pkey_passphrase = decrypt_password(config["ssh_pkey_passphrase_ciphertext"], config["ssh_pkey_passphrase_nonce"])
    else:
        ssh_password = config.get("ssh_password")
        pkey_passphrase = config.get("ssh_pkey_passphrase")

    ssh_pkey = config.get("ssh_pkey_path") if config.get("ssh_pkey_path") else None
    ssh_host = config.get("ssh_host")
    ssh_port = int(config.get("ssh_port", 22) or 22)
    ssh_username = config.get("ssh_username")

    target_host = config.get("host")
    target_port = int(config.get("port", 3306) or 3306)

    tunnel_type = "managed_datasource" if is_managed else "temporary_test"
    logger.info(
        "Starting %s SSH Tunnel: Jumpbox %s:%s -> Target %s:%s",
        tunnel_type, ssh_host, ssh_port, target_host, target_port
    )

    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_username,
        ssh_password=ssh_password,
        ssh_pkey=ssh_pkey,
        ssh_private_key_password=pkey_passphrase,
        remote_bind_address=(target_host, target_port),
        local_bind_address=("127.0.0.1", 0),
        keepalive=30,
    )
    tunnel.start()
    return tunnel


def open_temporary_tunnel(config: dict[str, Any]) -> SSHTunnelForwarder:
    """Open a temporary SSH tunnel for test connections, mirroring keepalive and mapping logic."""
    return _create_physical_tunnel_forwarder(config, is_managed=False)


class TunnelManager:
    def __init__(self) -> None:
        self._tunnels: dict[str, TunnelInstance] = {}
        self._lock = threading.Lock()

    def get_tunnel_state(self, datasource_id: str) -> str:
        with self._lock:
            instance = self._tunnels.get(datasource_id)
            if not instance:
                return TunnelState.CLOSED
            return instance.state

    def close_tunnel(self, datasource_id: str) -> None:
        with self._lock:
            instance = self._tunnels.pop(datasource_id, None)
            if instance:
                instance.state = TunnelState.CLOSED
                try:
                    instance.tunnel.stop()
                except Exception as e:
                    logger.error("Error stopping tunnel for %s: %s", datasource_id, e)

    def close_all(self) -> None:
        with self._lock:
            for ds_id, instance in list(self._tunnels.items()):
                instance.state = TunnelState.CLOSED
                try:
                    instance.tunnel.stop()
                except Exception as e:
                    logger.error("Error stopping tunnel for %s: %s", ds_id, e)
            self._tunnels.clear()

    def health_check(self, datasource_id: str) -> bool:
        """Validate that the tunnel object and local bind socket are alive."""
        with self._lock:
            instance = self._tunnels.get(datasource_id)

        if not instance:
            return False

        if not instance.tunnel.is_active:
            instance.state = TunnelState.STALE
            return False

        try:
            port = instance.tunnel.local_bind_port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(("127.0.0.1", port))
            instance.state = TunnelState.CONNECTED
            return True
        except Exception as e:
            logger.warning(
                "Tunnel health probe failed on port %s for %s: %s",
                instance.tunnel.local_bind_port,
                datasource_id,
                e,
            )
            instance.state = TunnelState.STALE
            return False

    def get_or_reconnect(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        """Get an active tunnel or self-heal a stale one."""
        ds_id = ds_dict.get("id") or f"temp_{ds_dict.get('host')}_{ds_dict.get('port')}"

        with self._lock:
            instance = self._tunnels.get(ds_id)

        if not instance:
            return self._create_tunnel(ds_id, ds_dict)

        if self.health_check(ds_id):
            return instance.tunnel

        logger.info("SSH Tunnel for %s went stale. Initiating self-healing auto-reconnect...", ds_id)
        with self._lock:
            instance.state = TunnelState.RECONNECTING

        try:
            try:
                instance.tunnel.stop()
            except Exception:
                pass

            new_tunnel = self._start_physical_tunnel(ds_dict)
            with self._lock:
                instance.tunnel = new_tunnel
                instance.state = TunnelState.CONNECTED
                instance.error_message = None
            logger.info("SSH Tunnel auto-reconnect successful for %s.", ds_id)
            return new_tunnel
        except Exception as e:
            logger.error("SSH Tunnel self-healing auto-reconnect failed for %s: %s", ds_id, e)
            with self._lock:
                instance.state = TunnelState.FAILED
                instance.error_message = str(e)
            raise DataSourceConnectionError(f"SSH 隧道连接已断开，自动尝试自愈重连失败: {str(e)}")

    def _create_tunnel(self, ds_id: str, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        logger.info("Creating new SSH tunnel for %s", ds_id)
        tunnel = self._start_physical_tunnel(ds_dict)
        instance = TunnelInstance(ds_id, ds_dict, tunnel)
        with self._lock:
            self._tunnels[ds_id] = instance
        return tunnel

    def _start_physical_tunnel(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        return _create_physical_tunnel_forwarder(ds_dict, is_managed=True)

    def cleanup_stale(self) -> None:
        with self._lock:
            for ds_id, instance in list(self._tunnels.items()):
                if not instance.tunnel.is_active:
                    logger.info("Purging dead inactive tunnel instance: %s", ds_id)
                    try:
                        instance.tunnel.stop()
                    except Exception:
                        pass
                    self._tunnels.pop(ds_id, None)


TUNNEL_MANAGER = TunnelManager()


def close_active_tunnel(datasource_id: str) -> None:
    """Close active SSH tunnel for a data source if it exists."""
    TUNNEL_MANAGER.close_tunnel(datasource_id)


def close_all_tunnels() -> None:
    """Close all active SSH tunnels on app shutdown."""
    TUNNEL_MANAGER.close_all()


def get_or_create_tunnel_for_dict(ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
    """Get or start an SSH tunnel with deep health probes and auto-reconnects."""
    return TUNNEL_MANAGER.get_or_reconnect(ds_dict)


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
    """Decrypt password and construct parameters for PyMySQL connection."""
    pw = decrypt_password(datasource_dict["password_ciphertext"], datasource_dict["password_nonce"])
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
    """Decrypt password and construct parameters for PostgreSQL connection."""
    pw = decrypt_password(datasource_dict["password_ciphertext"], datasource_dict["password_nonce"])
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


def test_connection(config: dict[str, Any]) -> dict[str, Any]:
    """
    Test connectivity to a database (MySQL, PostgreSQL, or SQLite).
    Returns basic database stats and checks if permissions are readonly or have write capabilities.
    """
    db_type = config.get("db_type", "mysql")

    if db_type == "sqlite":
        db_path = _require_existing_sqlite_file(config.get("database_name", ""))
        import os
        import sqlite3

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

                readonly = not os.access(db_path, os.W_OK)

                return {
                    "ok": True,
                    "serverVersion": f"SQLite {version}",
                    "readonly": readonly,
                    "tablesCount": tables_count,
                    "warnings": [],
                    "message": "SQLite 数据库连接测试成功！",
                }
            finally:
                conn.close()
        except Exception as e:
            if isinstance(e, DataSourceConnectionError):
                raise e
            raise DataSourceConnectionError(f"无法建立 SQLite 数据库连接，请检查路径配置。错误: {str(e)}")

    if db_type == "postgresql":
        host = config.get("host", "")
        port = config.get("port", 5432)
        database_name = config.get("database_name", "")
        username = config.get("username", "")
        password = config.get("password", "")

        if not host or not database_name or not username:
            raise DataSourceConnectionError("Missing host, database name, or username configuration.")

        temp_tunnel = None
        try:
            test_host = host
            test_port = port

            if config.get("ssh_enabled"):
                try:
                    if config.get("is_managed"):
                        temp_tunnel = get_or_create_tunnel_for_dict(config)
                    else:
                        temp_tunnel = open_temporary_tunnel(config)
                    test_host = "127.0.0.1"
                    test_port = temp_tunnel.local_bind_port
                except Exception as se:
                    raise DataSourceConnectionError(f"无法建立 SSH 隧道，请检查跳板机配置。错误: {str(se)}")

            import psycopg2

            conn = psycopg2.connect(
                host=test_host,
                port=test_port,
                user=username,
                password=password,
                database=database_name,
                connect_timeout=5,
                **build_postgres_ssl_params(config),
            )
            try:
                with conn.cursor() as cursor:  # type: ignore[attr-defined]
                    cursor.execute("SELECT version()")
                    version_row = cursor.fetchone()
                    version = str(version_row[0]) if version_row else "unknown"

                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM information_schema.tables
                        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    """)
                    tables_row = cursor.fetchone()
                    tables_count = int(tables_row[0]) if tables_row else 0

                    cursor.execute("SELECT current_setting('transaction_read_only')")
                    ro_res = cursor.fetchone()
                    readonly = (ro_res[0] == "on") if ro_res else False

                    warnings = []
                    if not readonly:
                        warnings.append("提示：当前数据库账号包含写入权限，建议在生产环境使用只读账号以保安全。")

                    return {
                        "ok": True,
                        "serverVersion": version,
                        "readonly": readonly,
                        "tablesCount": tables_count,
                        "warnings": warnings,
                        "message": "PostgreSQL 数据库连接测试成功！",
                    }
            finally:
                conn.close()
        except Exception as e:
            if isinstance(e, DataSourceConnectionError):
                raise e
            raise DataSourceConnectionError(f"无法建立 PostgreSQL 数据库连接，请检查配置信息。错误详情: {str(e)}")
        finally:
            if temp_tunnel and not config.get("is_managed"):
                try:
                    temp_tunnel.stop()
                except Exception:
                    pass

    host = config.get("host", "")
    port = config.get("port", 3306)
    database_name = config.get("database_name", "")
    username = config.get("username", "")
    password = config.get("password", "")

    if not host or not database_name or not username:
        raise DataSourceConnectionError("Missing host, database name, or username configuration.")

    temp_tunnel = None
    try:
        test_host = host
        test_port = port

        if config.get("ssh_enabled"):
            try:
                if config.get("is_managed"):
                    temp_tunnel = get_or_create_tunnel_for_dict(config)
                else:
                    temp_tunnel = open_temporary_tunnel(config)
                test_host = "127.0.0.1"
                test_port = temp_tunnel.local_bind_port
            except Exception as se:
                raise DataSourceConnectionError(f"无法建立 SSH 隧道，请检查跳板机配置。错误: {str(se)}")

        conn = pymysql.connect(  # type: ignore[assignment]
            host=test_host,
            port=test_port,
            user=username,
            password=password,
            database=database_name,
            charset="utf8mb4",
            connect_timeout=5,
            **build_mysql_ssl_params(config),
        )
        try:
            with conn.cursor() as cursor:  # type: ignore[attr-defined]
                cursor.execute("SELECT VERSION()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                    (database_name,),
                )
                tables_row = cursor.fetchone()
                tables_count = int(tables_row[0]) if tables_row else 0

                readonly = True
                warnings = []
                try:
                    cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
                    grants = [row[0] for row in cursor.fetchall()]
                    for grant in grants:
                        grant_upper = grant.upper()
                        if "ALL PRIVILEGES" in grant_upper or any(op in grant_upper for op in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER"]):
                            readonly = False
                            break
                except Exception:
                    try:
                        cursor.execute("SHOW VARIABLES LIKE 'read_only'")
                        res = cursor.fetchone()
                        if res and res[1] == "ON":
                            readonly = True
                        else:
                            readonly = False
                    except Exception:
                        readonly = False

                if not readonly:
                    warnings.append("提示：当前数据库账号包含写入权限(INSERT/UPDATE/DELETE/DROP)，建议在生产环境使用只读只查的只读账号以保安全。")

                return {
                    "ok": True,
                    "serverVersion": version,
                    "readonly": readonly,
                    "tablesCount": tables_count,
                    "warnings": warnings,
                    "message": "数据库连接测试成功！",
                }
        finally:
            conn.close()
    except Exception as e:
        if isinstance(e, DataSourceConnectionError):
            raise e
        raise DataSourceConnectionError(f"无法建立数据库连接，请检查配置信息。错误详情: {str(e)}")
    finally:
        if temp_tunnel and not config.get("is_managed"):
            try:
                temp_tunnel.stop()
            except Exception:
                pass


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
        "password_ciphertext": ds.password_ciphertext,
        "password_nonce": ds.password_nonce,
        "ssh_enabled": ds.ssh_enabled,
        "ssh_host": ds.ssh_host,
        "ssh_port": ds.ssh_port,
        "ssh_username": ds.ssh_username,
        "ssh_password_ciphertext": ds.ssh_password_ciphertext,
        "ssh_password_nonce": ds.ssh_password_nonce,
        "ssh_pkey_path": ds.ssh_pkey_path,
        "ssh_pkey_passphrase_ciphertext": ds.ssh_pkey_passphrase_ciphertext,
        "ssh_pkey_passphrase_nonce": ds.ssh_pkey_passphrase_nonce,
        "ssl_enabled": ds.ssl_enabled,
        "ssl_ca_path": ds.ssl_ca_path,
        "ssl_cert_path": ds.ssl_cert_path,
        "ssl_key_path": ds.ssl_key_path,
        "ssl_verify_identity": ds.ssl_verify_identity,
    }
