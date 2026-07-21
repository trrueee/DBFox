"""Private pooled-driver adapters owned by :mod:`engine.connectivity.factory`.

Pool creators retain only non-secret connection metadata plus an opaque vault
credential id.  A database password is resolved only in the short-lived
creator invocation that opens a new DBAPI connection; it is never captured in
the long-lived ``QueuePool`` creator closure.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pymysql
from sqlalchemy.pool import QueuePool

from engine.connectivity.profile import ConnectionProfile
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialKind, CredentialVault
from engine.sql.pool_registry import get_pool_registry


def _pool_key(
    profile: ConnectionProfile,
    *,
    dialect: str,
    host: str,
    port: int,
) -> tuple[str, int, str, str, str, int]:
    """Build a resource key without resolved secrets.

    The endpoint stays in the key because a healthy SSH profile can reconnect
    to a different local bind port without changing its persisted generation.
    """
    resource_key = profile.managed_resource_key
    if resource_key is None:
        raise DataSourceConnectionError("Only managed datasource profiles may use a connection pool.")
    return (*resource_key.pool_prefix, dialect, host, port)


def _resolve_password(vault: CredentialVault, credential_id: str | None) -> str:
    if not credential_id:
        raise DataSourceConnectionError(
            "A password credential is required for network datasource connections."
        )
    password = vault.get(credential_id, expected_kind=CredentialKind.DATASOURCE_PASSWORD)
    if password is None:
        raise DataSourceConnectionError(
            "Credential reference was not found or has the wrong kind."
        )
    return password


def _without_password(params: Mapping[str, Any]) -> dict[str, Any]:
    """Reject secret-bearing params before a creator closure can retain them."""
    if "password" in params:
        raise ValueError("Pooled connection parameters must not contain a resolved password.")
    return dict(params)


def _get_postgres_pool(
    profile: ConnectionProfile,
    *,
    host: str,
    port: int,
    params: Mapping[str, Any],
    vault: CredentialVault,
) -> QueuePool:
    """Get a PostgreSQL pool keyed by its managed resource generation."""
    pool_params = _without_password(params)
    pool_params.update({"host": host, "port": port, "connect_timeout": 5})
    pool_key = _pool_key(profile, dialect="postgresql", host=host, port=port)
    credential_id = profile.password_credential_id

    def creator() -> Any:
        import psycopg2

        password = _resolve_password(vault, credential_id)
        return psycopg2.connect(**pool_params, password=password)

    return get_pool_registry().get_or_create(
        pool_key,
        cast(Any, creator),
        pool_size=5,
        max_overflow=10,
        recycle=1800,
        timeout=10.0,
    )


def _get_mysql_pool(
    profile: ConnectionProfile,
    *,
    host: str,
    port: int,
    params: Mapping[str, Any],
    vault: CredentialVault,
) -> QueuePool:
    """Get a MySQL pool keyed by its managed resource generation."""
    pool_params = _without_password(params)
    pool_params.update(
        {
            "host": host,
            "port": port,
            "connect_timeout": 5,
            "read_timeout": 30,
            "write_timeout": 30,
        }
    )
    pool_key = _pool_key(profile, dialect="mysql", host=host, port=port)
    credential_id = profile.password_credential_id

    def creator() -> pymysql.Connection:
        password = _resolve_password(vault, credential_id)
        return pymysql.connect(**pool_params, password=password)

    return get_pool_registry().get_or_create(
        pool_key,
        cast(Any, creator),
        pool_size=5,
        max_overflow=10,
        recycle=1800,
        timeout=10.0,
    )


def _ping_mysql_connection(connection_proxy: Any) -> Any:
    """Validate and unwrap a raw PyMySQL connection checked out from QueuePool."""
    raw_connection: Any = (
        getattr(connection_proxy, "dbapi_connection", None)
        or getattr(connection_proxy, "connection", None)
        or connection_proxy
    )
    raw_connection.ping(reconnect=True)
    return raw_connection
