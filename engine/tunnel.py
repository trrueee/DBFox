from __future__ import annotations

import logging
import socket
import threading
from typing import Any

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
