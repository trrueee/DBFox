"""Immutable, secret-free connection configuration."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Mapping

from engine.errors import DataSourceConnectionError


class ConnectionPurpose(StrEnum):
    """The operation requesting a database connection."""

    QUERY = "query"
    STREAMING_EXPORT = "streaming_export"
    DRY_RUN = "dry_run"
    EXPLAIN = "explain"
    SCHEMA_SYNC = "schema_sync"
    HEALTH_CHECK = "health_check"
    CONNECTION_TEST = "connection_test"
    TABLE_DESIGN = "table_design"
    TEST_DATA = "test_data"
    BACKUP = "backup"
    RESTORE = "restore"


_PLAINTEXT_SECRET_FIELDS = frozenset({"password", "ssh_password", "ssh_pkey_passphrase"})
_SUPPORTED_DIALECTS = frozenset({"sqlite", "duckdb", "mysql", "postgresql"})


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(config: Mapping[str, Any], field: str, message: str) -> str:
    value = _optional_text(config.get(field))
    if value is None:
        raise DataSourceConnectionError(message)
    return value


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise DataSourceConnectionError("Connection boolean configuration is invalid.")


def _port(value: Any, *, default: int, field: str) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise DataSourceConnectionError(f"{field} must be a valid TCP port.") from exc
    if not 1 <= port <= 65_535:
        raise DataSourceConnectionError(f"{field} must be between 1 and 65535.")
    return port


def _connection_generation(value: Any, *, managed: bool) -> int | None:
    """Validate the persisted generation that fences managed resources.

    A datasource update changes connection metadata and/or credential references
    in one metadata transaction.  The generation is incremented in that same
    transaction and makes an old in-memory profile unusable immediately after
    the update commits.  Transient connection-test profiles intentionally do
    not have one.
    """
    if value is None:
        if managed:
            raise DataSourceConnectionError(
                "Managed datasource configuration is missing its connection generation."
            )
        return None
    try:
        generation = int(value)
    except (TypeError, ValueError) as exc:
        raise DataSourceConnectionError(
            "Connection generation must be a positive integer."
        ) from exc
    if generation < 1:
        raise DataSourceConnectionError("Connection generation must be a positive integer.")
    return generation


@dataclass(frozen=True, slots=True)
class ManagedDatasourceResourceKey:
    """Identity for all reusable resources of one persisted datasource version.

    The resource key has no resolved secret.  It deliberately contains both a
    monotonic generation and a metadata/credential-reference fingerprint: a
    profile changed from A -> B -> A must not resurrect the old A pool/tunnel.
    """

    datasource_id: str
    connection_generation: int
    profile_fingerprint: str

    @property
    def pool_prefix(self) -> tuple[str, int, str]:
        """Prefix shared by all pools created for this exact profile version."""
        return (
            self.datasource_id,
            self.connection_generation,
            self.profile_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    """A validated connection description containing opaque credential IDs only."""

    datasource_id: str | None
    dialect: str
    host: str | None
    port: int | None
    database_name: str
    username: str | None
    password_credential_id: str | None
    ssh_enabled: bool
    ssh_host: str | None
    ssh_port: int
    ssh_username: str | None
    ssh_password_credential_id: str | None
    ssh_pkey_path: str | None
    ssh_key_passphrase_credential_id: str | None
    ssl_enabled: bool
    ssl_ca_path: str | None
    ssl_cert_path: str | None
    ssl_key_path: str | None
    ssl_verify_identity: bool
    is_managed: bool
    connection_generation: int | None

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "ConnectionProfile":
        """Validate metadata while rejecting plaintext credentials at the boundary."""
        unexpected_secret_fields = sorted(
            field for field in _PLAINTEXT_SECRET_FIELDS if field in config
        )
        if unexpected_secret_fields:
            raise DataSourceConnectionError(
                "Plaintext credentials are not accepted by the connection boundary."
            )

        raw_dialect = (_optional_text(config.get("db_type")) or "mysql").lower()
        dialect = "postgresql" if raw_dialect == "postgres" else raw_dialect
        if dialect not in _SUPPORTED_DIALECTS:
            raise DataSourceConnectionError("Unsupported datasource dialect.")

        database_name = _required_text(
            config,
            "database_name",
            "A database name or SQLite database file path is required.",
        )
        datasource_id = _optional_text(config.get("id") or config.get("datasource_id"))
        is_managed = _bool(config.get("is_managed"), default=False)
        connection_generation = _connection_generation(
            config.get("connection_generation"),
            managed=is_managed,
        )
        ssl_enabled = _bool(config.get("ssl_enabled"), default=False)
        ssl_verify_identity = _bool(config.get("ssl_verify_identity"), default=True)

        if dialect in {"sqlite", "duckdb"}:
            if _bool(config.get("ssh_enabled"), default=False):
                raise DataSourceConnectionError(
                    f"{dialect.title()} connections cannot use an SSH tunnel."
                )
            if _optional_text(config.get("password_credential_id")) is not None:
                raise DataSourceConnectionError(
                    f"{dialect.title()} connections must not use a password credential."
                )
            return cls(
                datasource_id=datasource_id,
                dialect=dialect,
                host=None,
                port=None,
                database_name=database_name,
                username=None,
                password_credential_id=None,
                ssh_enabled=False,
                ssh_host=None,
                ssh_port=22,
                ssh_username=None,
                ssh_password_credential_id=None,
                ssh_pkey_path=None,
                ssh_key_passphrase_credential_id=None,
                ssl_enabled=False,
                ssl_ca_path=None,
                ssl_cert_path=None,
                ssl_key_path=None,
                ssl_verify_identity=True,
                is_managed=is_managed,
                connection_generation=connection_generation,
            )

        host = _required_text(config, "host", "A network datasource host is required.")
        username = _required_text(config, "username", "A network datasource username is required.")
        password_credential_id = _required_text(
            config,
            "password_credential_id",
            "A password credential is required for network datasource connections.",
        )
        default_port = 5432 if dialect == "postgresql" else 3306
        port = _port(config.get("port"), default=default_port, field="port")
        ssh_enabled = _bool(config.get("ssh_enabled"), default=False)
        ssh_host = _optional_text(config.get("ssh_host"))
        ssh_username = _optional_text(config.get("ssh_username"))
        ssh_password_credential_id = _optional_text(config.get("ssh_password_credential_id"))
        ssh_pkey_path = _optional_text(config.get("ssh_pkey_path"))
        ssh_key_passphrase_credential_id = _optional_text(
            config.get("ssh_key_passphrase_credential_id")
        )
        if ssh_enabled:
            if ssh_host is None or ssh_username is None:
                raise DataSourceConnectionError("SSH tunnel host and username are required.")
            if ssh_password_credential_id is None and ssh_pkey_path is None:
                raise DataSourceConnectionError(
                    "An SSH password credential or private key path is required."
                )

        return cls(
            datasource_id=datasource_id,
            dialect=dialect,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            password_credential_id=password_credential_id,
            ssh_enabled=ssh_enabled,
            ssh_host=ssh_host,
            ssh_port=_port(config.get("ssh_port"), default=22, field="ssh_port"),
            ssh_username=ssh_username,
            ssh_password_credential_id=ssh_password_credential_id,
            ssh_pkey_path=ssh_pkey_path,
            ssh_key_passphrase_credential_id=ssh_key_passphrase_credential_id,
            ssl_enabled=ssl_enabled,
            ssl_ca_path=_optional_text(config.get("ssl_ca_path")),
            ssl_cert_path=_optional_text(config.get("ssl_cert_path")),
            ssl_key_path=_optional_text(config.get("ssl_key_path")),
            ssl_verify_identity=ssl_verify_identity,
            is_managed=is_managed,
            connection_generation=connection_generation,
        )

    @property
    def profile_fingerprint(self) -> str:
        """Stable identity for connection metadata and opaque credential IDs.

        It intentionally excludes ``connection_generation``.  The generation
        is a separate member of :class:`ManagedDatasourceResourceKey`, so a
        later update that returns to the same metadata still receives a new
        resource identity.
        """
        payload = {
            "datasource_id": self.datasource_id,
            "dialect": self.dialect,
            "host": self.host,
            "port": self.port,
            "database_name": self.database_name,
            "username": self.username,
            "password_credential_id": self.password_credential_id,
            "ssh_enabled": self.ssh_enabled,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "ssh_username": self.ssh_username,
            "ssh_password_credential_id": self.ssh_password_credential_id,
            "ssh_pkey_path": self.ssh_pkey_path,
            "ssh_key_passphrase_credential_id": self.ssh_key_passphrase_credential_id,
            "ssl_enabled": self.ssl_enabled,
            "ssl_ca_path": self.ssl_ca_path,
            "ssl_cert_path": self.ssl_cert_path,
            "ssl_key_path": self.ssl_key_path,
            "ssl_verify_identity": self.ssl_verify_identity,
            "is_managed": self.is_managed,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return f"conn_{sha256(canonical.encode('utf-8')).hexdigest()}"

    @property
    def fingerprint(self) -> str:
        """Backward-compatible name for the secret-free profile fingerprint."""
        return self.profile_fingerprint

    @property
    def managed_resource_key(self) -> ManagedDatasourceResourceKey | None:
        """Return the reusable-resource identity for a persisted datasource."""
        if not self.is_managed:
            return None
        if self.datasource_id is None or self.connection_generation is None:
            raise DataSourceConnectionError(
                "Managed datasource configuration is incomplete."
            )
        return ManagedDatasourceResourceKey(
            datasource_id=self.datasource_id,
            connection_generation=self.connection_generation,
            profile_fingerprint=self.profile_fingerprint,
        )

    def tunnel_config(self) -> dict[str, Any]:
        """Return only opaque metadata required by the tunnel subsystem."""
        return {
            "id": self.datasource_id,
            "host": self.host,
            "port": self.port,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "ssh_username": self.ssh_username,
            "ssh_password_credential_id": self.ssh_password_credential_id,
            "ssh_pkey_path": self.ssh_pkey_path,
            "ssh_key_passphrase_credential_id": self.ssh_key_passphrase_credential_id,
            "connection_generation": self.connection_generation,
            "connection_fingerprint": self.profile_fingerprint,
        }
