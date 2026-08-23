"""Secret-free direct connection primitives owned by the Data capability."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import stat
from typing import Any


class ConnectionConfigurationError(ValueError):
    """A secret-free connection profile violates a driver safety contract."""


def _value(config: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _optional_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def existing_regular_file(value: str, *, label: str) -> Path:
    """Resolve an existing non-symlink file used by an embedded database."""

    try:
        path = Path(value).expanduser()
        path_stat = path.lstat()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ConnectionConfigurationError(f"{label} database file is unavailable") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise ConnectionConfigurationError(f"{label} database file is unavailable")
    return path.resolve()


def build_mysql_ssl_params(config: Mapping[str, Any] | object) -> dict[str, Any]:
    if not _value(config, "ssl_enabled", False):
        return {}
    ca_path = _optional_path(_value(config, "ssl_ca_path"))
    cert_path = _optional_path(_value(config, "ssl_cert_path"))
    key_path = _optional_path(_value(config, "ssl_key_path"))
    verify_identity = bool(_value(config, "ssl_verify_identity", True))
    if verify_identity and not ca_path:
        raise ConnectionConfigurationError(
            "MySQL TLS identity verification requires a CA certificate path"
        )
    params: dict[str, Any] = {
        "ssl_verify_cert": True,
        "ssl_verify_identity": verify_identity,
    }
    for key, value in (
        ("ssl_ca", ca_path),
        ("ssl_cert", cert_path),
        ("ssl_key", key_path),
    ):
        if value:
            params[key] = value
    return params


def build_postgres_ssl_params(config: Mapping[str, Any] | object) -> dict[str, Any]:
    if not _value(config, "ssl_enabled", False):
        return {}
    ca_path = _optional_path(_value(config, "ssl_ca_path"))
    cert_path = _optional_path(_value(config, "ssl_cert_path"))
    key_path = _optional_path(_value(config, "ssl_key_path"))
    verify_identity = bool(_value(config, "ssl_verify_identity", True))
    if verify_identity and not ca_path:
        raise ConnectionConfigurationError(
            "PostgreSQL TLS identity verification requires a CA certificate path"
        )
    params: dict[str, Any] = {
        "sslmode": (
            "verify-full"
            if verify_identity
            else "verify-ca" if ca_path else "require"
        )
    }
    for key, value in (
        ("sslrootcert", ca_path),
        ("sslcert", cert_path),
        ("sslkey", key_path),
    ):
        if value:
            params[key] = value
    return params


def network_driver_params(
    *,
    provider: str,
    host: str,
    port: int,
    username: str,
    database: str,
    config: Mapping[str, Any] | object,
) -> dict[str, Any]:
    if provider == "mysql":
        params: dict[str, Any] = {
            "host": host,
            "port": port,
            "user": username,
            "database": database,
            "charset": "utf8mb4",
            "connect_timeout": 5,
            "read_timeout": 10,
            "write_timeout": 10,
        }
        params.update(build_mysql_ssl_params(config))
        return params
    if provider == "postgresql":
        params = {
            "host": host,
            "port": port,
            "user": username,
            "database": database,
        }
        params.update(build_postgres_ssl_params(config))
        return params
    raise ConnectionConfigurationError("Unsupported database provider")


def open_network_connection(provider: str, params: Mapping[str, Any]) -> Any:
    """Open one DBAPI connection from already validated ephemeral parameters."""

    if provider == "mysql":
        import pymysql

        return pymysql.connect(**dict(params))
    if provider == "postgresql":
        import psycopg2

        return psycopg2.connect(**dict(params), connect_timeout=5)
    raise ConnectionConfigurationError("Unsupported database provider")
