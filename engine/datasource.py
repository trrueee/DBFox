from typing import Any

import pymysql

from engine.crypto import decrypt_password
from engine.errors import DataSourceConnectionError

import threading
import socket
import logging
from sshtunnel import SSHTunnelForwarder

logger = logging.getLogger("databox.tunnel")

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
                    logger.error(f"Error stopping tunnel for {datasource_id}: {e}")

    def close_all(self) -> None:
        with self._lock:
            for ds_id, instance in list(self._tunnels.items()):
                instance.state = TunnelState.CLOSED
                try:
                    instance.tunnel.stop()
                except Exception as e:
                    logger.error(f"Error stopping tunnel for {ds_id}: {e}")
            self._tunnels.clear()

    def health_check(self, datasource_id: str) -> bool:
        """
        Performs deep health check on the specified tunnel by validating socket availability.
        """
        instance = None
        with self._lock:
            instance = self._tunnels.get(datasource_id)
        
        if not instance:
            return False

        if not instance.tunnel.is_active:
            instance.state = TunnelState.STALE
            return False

        # Attempt to probe the local bind port via a quick TCP connection test
        try:
            port = instance.tunnel.local_bind_port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(('127.0.0.1', port))
            instance.state = TunnelState.CONNECTED
            return True
        except Exception as e:
            logger.warning(f"Tunnel health probe failed on port {instance.tunnel.local_bind_port} for {datasource_id}: {e}")
            instance.state = TunnelState.STALE
            return False

    def get_or_reconnect(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        """
        Retrieves active tunnel or automatically triggers self-healing re-connections if stale.
        """
        ds_id = ds_dict.get("id")
        if not ds_id:
            ds_id = f"temp_{ds_dict.get('host')}_{ds_dict.get('port')}"

        with self._lock:
            instance = self._tunnels.get(ds_id)

        if not instance:
            return self._create_tunnel(ds_id, ds_dict)

        # Deep health check probe
        is_healthy = self.health_check(ds_id)
        if is_healthy:
            return instance.tunnel

        logger.info(f"SSH Tunnel for {ds_id} went stale. Initiating self-healing auto-reconnect...")
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
            logger.info(f"SSH Tunnel auto-reconnect successful for {ds_id}.")
            return new_tunnel
        except Exception as e:
            logger.error(f"SSH Tunnel self-healing auto-reconnect failed for {ds_id}: {e}")
            with self._lock:
                instance.state = TunnelState.FAILED
                instance.error_message = str(e)
            raise DataSourceConnectionError(f"SSH 隧道连接已断开，自动尝试自愈重连失败: {str(e)}")

    def _create_tunnel(self, ds_id: str, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        logger.info(f"Creating new SSH tunnel for {ds_id}")
        tunnel = self._start_physical_tunnel(ds_dict)
        instance = TunnelInstance(ds_id, ds_dict, tunnel)
        with self._lock:
            self._tunnels[ds_id] = instance
        return tunnel

    def _start_physical_tunnel(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        ssh_password = None
        if ds_dict.get("ssh_password_ciphertext") and ds_dict.get("ssh_password_nonce"):
            ssh_password = decrypt_password(ds_dict["ssh_password_ciphertext"], ds_dict["ssh_password_nonce"])

        pkey_passphrase = None
        if ds_dict.get("ssh_pkey_passphrase_ciphertext") and ds_dict.get("ssh_pkey_passphrase_nonce"):
            pkey_passphrase = decrypt_password(ds_dict["ssh_pkey_passphrase_ciphertext"], ds_dict["ssh_pkey_passphrase_nonce"])

        ssh_pkey = ds_dict.get("ssh_pkey_path") if ds_dict.get("ssh_pkey_path") else None
        ssh_host = ds_dict.get("ssh_host")
        ssh_port = int(ds_dict.get("ssh_port", 22))
        ssh_username = ds_dict.get("ssh_username")

        target_host = ds_dict.get("host")
        target_port = int(ds_dict.get("port", 3306))

        tunnel = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_username,
            ssh_password=ssh_password,
            ssh_pkey=ssh_pkey,
            ssh_private_key_password=pkey_passphrase,
            remote_bind_address=(target_host, target_port),
            local_bind_address=('127.0.0.1', 0),
            # Protocol transport-level KeepAlive (every 30s) to bypass idle remote firewall drops
            keepalive=30,
        )
        tunnel.start()
        return tunnel

    def cleanup_stale(self) -> None:
        with self._lock:
            for ds_id, instance in list(self._tunnels.items()):
                if not instance.tunnel.is_active:
                    logger.info(f"Purging dead inactive tunnel instance: {ds_id}")
                    try:
                        instance.tunnel.stop()
                    except Exception:
                        pass
                    self._tunnels.pop(ds_id, None)

# Instantiate global TunnelManager to serve all background drivers and connection requests
TUNNEL_MANAGER = TunnelManager()

def close_active_tunnel(datasource_id: str) -> None:
    """Close active SSH tunnel for a data source if it exists"""
    TUNNEL_MANAGER.close_tunnel(datasource_id)

def close_all_tunnels() -> None:
    """Close all active SSH tunnels on app shutdown"""
    TUNNEL_MANAGER.close_all()

def get_or_create_tunnel_for_dict(ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
    """Gets or starts an SSH tunnel with deep health probes and auto-reconnects"""
    return TUNNEL_MANAGER.get_or_reconnect(ds_dict)

def _normalized_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def build_mysql_ssl_params(config: dict[str, Any]) -> dict[str, Any]:
    """Build PyMySQL SSL parameters with certificate verification enabled."""
    if not config.get("ssl_enabled"):
        return {}

    ca_path = _normalized_optional_path(config.get("ssl_ca_path"))
    cert_path = _normalized_optional_path(config.get("ssl_cert_path"))
    key_path = _normalized_optional_path(config.get("ssl_key_path"))
    verify_identity = bool(config.get("ssl_verify_identity", True))

    if verify_identity and not ca_path:
        raise DataSourceConnectionError(
            "SSL identity verification requires a CA certificate path."
        )

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

def get_mysql_connection_params(datasource_dict: dict[str, Any]) -> dict[str, Any]:
    """Decrypt password and construct parameters for PyMySQL connection"""
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
    """Decrypt password and construct parameters for PostgreSQL connection"""
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
    return params

def test_connection(config: dict[str, Any]) -> dict[str, Any]:
    """
    Test connectivity to a database (MySQL, PostgreSQL, or SQLite).
    Returns basic database stats and checks if permissions are readonly or have write capabilities.
    """
    db_type = config.get("db_type", "mysql")

    # 1. Handle SQLite Database Connection Test
    if db_type == "sqlite":
        db_path = config.get("database_name", "")
        if not db_path:
            raise DataSourceConnectionError("未提供 SQLite 数据库文件路径。")

        import os
        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=5)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT sqlite_version()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                tables_row = cursor.fetchone()
                tables_count = int(tables_row[0]) if tables_row else 0

                readonly = False
                if os.path.exists(db_path) and not os.access(db_path, os.W_OK):
                    readonly = True

                return {
                    "ok": True,
                    "serverVersion": f"SQLite {version}",
                    "readonly": readonly,
                    "tablesCount": tables_count,
                    "warnings": [],
                    "message": "SQLite 数据库连接测试成功！"
                }
            finally:
                conn.close()
        except Exception as e:
            raise DataSourceConnectionError(f"无法建立 SQLite 数据库连接，请检查路径配置。错误: {str(e)}")

    # 2. Handle PostgreSQL Database Connection Test
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
                ssh_host = config.get("ssh_host")
                ssh_port = int(config.get("ssh_port", 22))
                ssh_username = config.get("ssh_username")
                ssh_password = config.get("ssh_password")
                ssh_pkey = config.get("ssh_pkey_path") if config.get("ssh_pkey_path") else None
                pkey_passphrase = config.get("ssh_pkey_passphrase")

                try:
                    temp_tunnel = SSHTunnelForwarder(
                        (ssh_host, ssh_port),
                        ssh_username=ssh_username,
                        ssh_password=ssh_password,
                        ssh_pkey=ssh_pkey,
                        ssh_private_key_password=pkey_passphrase,
                        remote_bind_address=(host, port),
                        local_bind_address=('127.0.0.1', 0),
                    )
                    temp_tunnel.start()
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
                connect_timeout=5
            )
            try:
                with conn.cursor() as cursor:  # type: ignore[attr-defined]
                    # Get PostgreSQL server version
                    cursor.execute("SELECT version()")
                    version_row = cursor.fetchone()
                    version = str(version_row[0]) if version_row else "unknown"

                    # Get count of tables in this database (non-system tables)
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    """)
                    tables_row = cursor.fetchone()
                    tables_count = int(tables_row[0]) if tables_row else 0

                    # Assess write permissions
                    cursor.execute("SELECT current_setting('transaction_read_only')")
                    ro_res = cursor.fetchone()
                    readonly = (ro_res[0] == 'on') if ro_res else False

                    warnings = []
                    if not readonly:
                        warnings.append("提示：当前数据库账号包含写入权限，建议在生产环境使用只读账号以保安全。")

                    return {
                        "ok": True,
                        "serverVersion": version,
                        "readonly": readonly,
                        "tablesCount": tables_count,
                        "warnings": warnings,
                        "message": "PostgreSQL 数据库连接测试成功！"
                    }
            finally:
                conn.close()
        except Exception as e:
            if isinstance(e, DataSourceConnectionError):
                raise e
            raise DataSourceConnectionError(f"无法建立 PostgreSQL 数据库连接，请检查配置信息。错误详情: {str(e)}")
        finally:
            if temp_tunnel:
                try:
                    temp_tunnel.stop()
                except Exception:
                    pass

    # 3. Handle Real MySQL Connection Test
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
            ssh_host = config.get("ssh_host")
            ssh_port = int(config.get("ssh_port", 22))
            ssh_username = config.get("ssh_username")
            ssh_password = config.get("ssh_password")
            ssh_pkey = config.get("ssh_pkey_path") if config.get("ssh_pkey_path") else None
            pkey_passphrase = config.get("ssh_pkey_passphrase")

            try:
                temp_tunnel = SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    ssh_username=ssh_username,
                    ssh_password=ssh_password,
                    ssh_pkey=ssh_pkey,
                    ssh_private_key_password=pkey_passphrase,
                    remote_bind_address=(host, port),
                    local_bind_address=('127.0.0.1', 0),
                )
                temp_tunnel.start()
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
                # Get MySQL server version
                cursor.execute("SELECT VERSION()")
                version_row = cursor.fetchone()
                version = str(version_row[0]) if version_row else "unknown"

                # Get count of tables in this database
                cursor.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                    (database_name,)
                )
                tables_row = cursor.fetchone()
                tables_count = int(tables_row[0]) if tables_row else 0

                # Assess write permissions by reading grants or querying table privileges
                readonly = True
                warnings = []
                try:
                    cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
                    grants = [row[0] for row in cursor.fetchall()]
                    # Check if grants contain unsafe privileges
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
                    "message": "数据库连接测试成功！"
                }
        finally:
            conn.close()
    except Exception as e:
        if isinstance(e, DataSourceConnectionError):
            raise e
        raise DataSourceConnectionError(f"无法建立数据库连接，请检查配置信息。错误详情: {str(e)}")
    finally:
        if temp_tunnel:
            try:
                temp_tunnel.stop()
            except Exception:
                pass
