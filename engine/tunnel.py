from __future__ import annotations

import logging
import socket
import threading
from typing import Any, TypeAlias

from sshtunnel import SSHTunnelForwarder

from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_message,
    log_unexpected_exception,
)
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialKind, get_credential_vault

logger = logging.getLogger("dbfox.tunnel")

TunnelResourceKey: TypeAlias = tuple[str, int, str]


def _managed_tunnel_key(config: dict[str, Any]) -> TunnelResourceKey:
    """Build the generation/profile key required for a managed SSH tunnel."""
    datasource_id = str(config.get("id") or "").strip()
    fingerprint = str(config.get("connection_fingerprint") or "").strip()
    raw_generation = config.get("connection_generation")
    if raw_generation is None:
        raise DataSourceConnectionError(
            "Managed SSH tunnel configuration is missing its connection generation."
        )
    try:
        generation = int(raw_generation)
    except (TypeError, ValueError) as exc:
        raise DataSourceConnectionError(
            "Managed SSH tunnel configuration is missing its connection generation."
        ) from exc
    if not datasource_id or not fingerprint or generation < 1:
        raise DataSourceConnectionError(
            "Managed SSH tunnel configuration is incomplete."
        )
    return (datasource_id, generation, fingerprint)


class TunnelState:
    CONNECTED = "connected"
    STALE = "stale"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSED = "closed"


class TunnelInstance:
    datasource_id: str
    resource_key: TunnelResourceKey
    ds_dict: dict[str, Any]
    tunnel: SSHTunnelForwarder
    state: str
    error_message: str | None

    def __init__(
        self,
        resource_key: TunnelResourceKey,
        ds_dict: dict[str, Any],
        tunnel: SSHTunnelForwarder,
    ) -> None:
        self.datasource_id = resource_key[0]
        self.resource_key = resource_key
        self.ds_dict = ds_dict
        self.tunnel = tunnel
        self.state = TunnelState.CONNECTED
        self.error_message = None


def _create_physical_tunnel_forwarder(config: dict[str, Any]) -> SSHTunnelForwarder:
    """Open an SSH tunnel using opaque credential references only."""
    ssh_password = None
    pkey_passphrase = None

    vault = get_credential_vault()
    ssh_password_id = config.get("ssh_password_credential_id")
    if ssh_password_id:
        ssh_password = vault.get(
            str(ssh_password_id),
            expected_kind=CredentialKind.SSH_PASSWORD,
        )
        if ssh_password is None:
            raise DataSourceConnectionError("SSH password credential was not found.")
    pkey_passphrase_id = config.get("ssh_key_passphrase_credential_id")
    if pkey_passphrase_id:
        pkey_passphrase = vault.get(
            str(pkey_passphrase_id),
            expected_kind=CredentialKind.SSH_KEY_PASSPHRASE,
        )
        if pkey_passphrase is None:
            raise DataSourceConnectionError("SSH key passphrase credential was not found.")

    ssh_pkey = config.get("ssh_pkey_path") if config.get("ssh_pkey_path") else None
    ssh_host = config.get("ssh_host")
    ssh_port = int(config.get("ssh_port", 22) or 22)
    ssh_username = config.get("ssh_username")

    target_host = config.get("host")
    target_port = int(config.get("port", 3306) or 3306)

    logger.info(
        "Starting SSH Tunnel: Jumpbox %s:%s -> Target %s:%s",
        ssh_host, ssh_port, target_host, target_port
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
    """Open a temporary SSH tunnel from vault-backed credential references."""
    return _create_physical_tunnel_forwarder(config)


class TunnelManager:
    def __init__(self) -> None:
        self._tunnels: dict[TunnelResourceKey, TunnelInstance] = {}
        self._lock = threading.Lock()

    def get_tunnel_state(self, datasource_id: str) -> str:
        with self._lock:
            instances = [
                instance
                for resource_key, instance in self._tunnels.items()
                if resource_key[0] == datasource_id
            ]
            if not instances:
                return TunnelState.CLOSED
            if any(instance.state == TunnelState.CONNECTED for instance in instances):
                return TunnelState.CONNECTED
            return instances[-1].state

    def close_tunnel(self, datasource_id: str) -> None:
        """Close every profile generation for a datasource.

        A configuration update may have briefly left an old tunnel object in
        flight while a new generation was opened.  Closing by datasource id is
        deliberately broad so no prior host/SSH credential profile survives.
        """
        instances: list[TunnelInstance] = []
        with self._lock:
            resource_keys = [key for key in self._tunnels if key[0] == datasource_id]
            for resource_key in resource_keys:
                instance = self._tunnels.pop(resource_key, None)
                if instance is not None:
                    instance.state = TunnelState.CLOSED
                    instances.append(instance)
        for instance in instances:
            try:
                instance.tunnel.stop()
            except Exception as exc:
                log_unexpected_exception(
                    logger,
                    operation=SafeLogOperation.SSH_TUNNEL_CLOSE,
                    exc=exc,
                )

    def close_all(self) -> None:
        with self._lock:
            for resource_key, instance in list(self._tunnels.items()):
                instance.state = TunnelState.CLOSED
                try:
                    instance.tunnel.stop()
                except Exception as exc:
                    log_unexpected_exception(
                        logger,
                        operation=SafeLogOperation.SSH_TUNNEL_CLOSE_ALL,
                        exc=exc,
                    )
            self._tunnels.clear()

    def health_check(self, resource_key: TunnelResourceKey) -> bool:
        """Validate that the tunnel object and local bind socket are alive."""
        with self._lock:
            instance = self._tunnels.get(resource_key)
            if not instance:
                return False

            if not instance.tunnel.is_active:
                instance.state = TunnelState.STALE
                return False

            port = instance.tunnel.local_bind_port

        # Connect socket outside the lock to prevent blocking other requests
        is_ok = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(("127.0.0.1", port))
            is_ok = True
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.SSH_TUNNEL_HEALTH_PROBE,
                exc=exc,
                level="warning",
            )

        with self._lock:
            instance = self._tunnels.get(resource_key)
            if not instance:
                return False
            if is_ok:
                instance.state = TunnelState.CONNECTED
                return True
            else:
                instance.state = TunnelState.STALE
                return False

    def get_or_reconnect(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        """Get an active tunnel or self-heal a stale one."""
        resource_key = _managed_tunnel_key(ds_dict)
        datasource_id = resource_key[0]

        with self._lock:
            instance = self._tunnels.get(resource_key)

        if not instance:
            return self._create_tunnel(resource_key, ds_dict)

        if self.health_check(resource_key):
            return instance.tunnel

        logger.info(
            "SSH Tunnel for %s generation %s went stale. Initiating self-healing auto-reconnect...",
            datasource_id,
            resource_key[1],
        )
        with self._lock:
            instance.state = TunnelState.RECONNECTING

        try:
            try:
                instance.tunnel.stop()
            except Exception as exc:
                log_unexpected_exception(
                    logger,
                    operation=SafeLogOperation.SSH_TUNNEL_RECONNECT_STOP_PREVIOUS,
                    exc=exc,
                    level="warning",
                )

            # The old pool creator used the prior local bind port.  Remove it
            # before publishing a reconnected tunnel so it cannot be reused if
            # the operating system later recycles that port.
            from engine.sql.pool_registry import get_pool_registry

            get_pool_registry().dispose_resource(resource_key)
            new_tunnel = self._start_physical_tunnel(ds_dict)
            with self._lock:
                instance.tunnel = new_tunnel
                instance.state = TunnelState.CONNECTED
                instance.error_message = None
            logger.info("SSH Tunnel auto-reconnect successful for %s.", datasource_id)
            return new_tunnel
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.SSH_TUNNEL_RECONNECT,
                exc=exc,
            )
            with self._lock:
                instance.state = TunnelState.FAILED
                instance.error_message = "SSH tunnel reconnection failed."
            raise DataSourceConnectionError(
                fixed_error_message(FixedErrorCode.DATASOURCE_CONNECTION_FAILED)
            ) from None

    def _create_tunnel(
        self,
        resource_key: TunnelResourceKey,
        ds_dict: dict[str, Any],
    ) -> SSHTunnelForwarder:
        logger.info(
            "Creating new SSH tunnel for %s generation %s",
            resource_key[0],
            resource_key[1],
        )
        tunnel = self._start_physical_tunnel(ds_dict)
        instance = TunnelInstance(resource_key, ds_dict, tunnel)
        with self._lock:
            self._tunnels[resource_key] = instance
        return tunnel

    def _start_physical_tunnel(self, ds_dict: dict[str, Any]) -> SSHTunnelForwarder:
        return _create_physical_tunnel_forwarder(ds_dict)

    def cleanup_stale(self) -> None:
        to_dispose: list[tuple[TunnelResourceKey, TunnelInstance]] = []
        with self._lock:
            for resource_key, instance in list(self._tunnels.items()):
                if not instance.tunnel.is_active:
                    logger.info("Purging dead inactive tunnel instance: %s", resource_key[0])
                    to_dispose.append((resource_key, instance))
                    self._tunnels.pop(resource_key, None)

        for _resource_key, instance in to_dispose:
            try:
                instance.tunnel.stop()
            except Exception as exc:
                log_unexpected_exception(
                    logger,
                    operation=SafeLogOperation.SSH_TUNNEL_CLEANUP_STALE,
                    exc=exc,
                    level="warning",
                )


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
