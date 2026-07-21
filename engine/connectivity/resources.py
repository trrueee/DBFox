"""Lifecycle management for non-secret connectivity resources."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Generator

from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.errors import DataSourceConnectionError
from engine.tunnel import get_or_create_tunnel_for_dict, open_temporary_tunnel


logger = logging.getLogger("dbfox.connectivity.resources")

TunnelOpener = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ConnectionEndpoint:
    """A non-secret endpoint made available for one connection operation."""

    host: str
    port: int
    tunnel: Any | None = field(default=None, repr=False, compare=False)
    temporary_tunnel: bool = False


class ConnectionResources:
    """Own the tunnel lifecycle and fail closed when an SSH tunnel cannot open."""

    def __init__(
        self,
        *,
        managed_tunnel_opener: TunnelOpener | None = None,
        temporary_tunnel_opener: TunnelOpener | None = None,
    ) -> None:
        self._managed_tunnel_opener = managed_tunnel_opener or get_or_create_tunnel_for_dict
        self._temporary_tunnel_opener = temporary_tunnel_opener or open_temporary_tunnel

    @contextmanager
    def endpoint_scope(
        self,
        profile: ConnectionProfile,
        purpose: ConnectionPurpose,
    ) -> Generator[ConnectionEndpoint, None, None]:
        if profile.dialect in {"sqlite", "duckdb"}:
            raise DataSourceConnectionError(
                f"{profile.dialect.title()} does not use a network connection endpoint."
            )
        if not profile.host or profile.port is None:
            raise DataSourceConnectionError("Network datasource endpoint is incomplete.")

        if not profile.ssh_enabled:
            yield ConnectionEndpoint(host=profile.host, port=profile.port)
            return

        temporary_tunnel = (
            purpose is ConnectionPurpose.CONNECTION_TEST and not profile.is_managed
        )
        opener = self._temporary_tunnel_opener if temporary_tunnel else self._managed_tunnel_opener
        tunnel: Any | None = None
        try:
            tunnel = opener(profile.tunnel_config())
            local_port = int(tunnel.local_bind_port)
        except DataSourceConnectionError:
            if temporary_tunnel and tunnel is not None:
                self._stop_temporary_tunnel(tunnel)
            raise
        except Exception as exc:
            if temporary_tunnel and tunnel is not None:
                self._stop_temporary_tunnel(tunnel)
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.DATASOURCE_TEST_SSH_TUNNEL,
                exc=exc,
                level="warning",
            )
            raise DataSourceConnectionError("Unable to establish the SSH tunnel.") from None

        endpoint = ConnectionEndpoint(
            host="127.0.0.1",
            port=local_port,
            tunnel=tunnel,
            temporary_tunnel=temporary_tunnel,
        )
        try:
            yield endpoint
        finally:
            if temporary_tunnel:
                self._stop_temporary_tunnel(tunnel)

    @staticmethod
    def _stop_temporary_tunnel(tunnel: Any) -> None:
        try:
            tunnel.stop()
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.DATASOURCE_TEST_SSH_TUNNEL,
                exc=exc,
                level="warning",
            )
