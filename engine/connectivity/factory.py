"""Build driver parameters from immutable profiles and vault-backed secrets."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
import stat
from typing import Any, Generator, Mapping

import pymysql

from engine.connectivity.lifecycle import (
    DatasourceResourceLifecycle,
    get_datasource_resource_lifecycle,
)
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.connectivity.resources import ConnectionEndpoint, ConnectionResources
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import (
    CredentialKind,
    CredentialVault,
    CredentialVaultUnavailableError,
    get_credential_vault,
)


@dataclass(frozen=True, slots=True)
class MySQLClientInvocation:
    """Ephemeral native-client inputs, valid only inside ``mysql_client_scope``.

    The database password is deliberately excluded from the public fields and
    is exposed to ``subprocess.run`` only through a one-use environment mapping.
    Keeping this object inside the factory scope prevents backup/restore code
    from resolving vault values or constructing driver parameter dictionaries.
    """

    host: str
    port: int
    username: str
    database: str
    _password: str = field(repr=False, compare=False)
    ssl_options: Mapping[str, str] = field(default_factory=dict)

    def environment(self) -> dict[str, str]:
        return {"MYSQL_PWD": self._password}


def _config_value(config: Mapping[str, Any] | ConnectionProfile, key: str, default: Any = None) -> Any:
    if isinstance(config, ConnectionProfile):
        return getattr(config, key, default)
    return config.get(key, default)


def _normalized_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_mysql_ssl_params(config: Mapping[str, Any] | ConnectionProfile) -> dict[str, Any]:
    """Build PyMySQL SSL parameters with certificate verification enabled."""
    if not _config_value(config, "ssl_enabled", False):
        return {}

    ca_path = _normalized_optional_path(_config_value(config, "ssl_ca_path"))
    cert_path = _normalized_optional_path(_config_value(config, "ssl_cert_path"))
    key_path = _normalized_optional_path(_config_value(config, "ssl_key_path"))
    verify_identity = bool(_config_value(config, "ssl_verify_identity", True))
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


def build_postgres_ssl_params(config: Mapping[str, Any] | ConnectionProfile) -> dict[str, Any]:
    """Build psycopg2 SSL parameters from the shared datasource SSL fields."""
    if not _config_value(config, "ssl_enabled", False):
        return {}

    ca_path = _normalized_optional_path(_config_value(config, "ssl_ca_path"))
    cert_path = _normalized_optional_path(_config_value(config, "ssl_cert_path"))
    key_path = _normalized_optional_path(_config_value(config, "ssl_key_path"))
    verify_identity = bool(_config_value(config, "ssl_verify_identity", True))
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


class ConnectionFactory:
    """The sole boundary that resolves datasource passwords for driver use."""

    def __init__(
        self,
        *,
        vault: CredentialVault | None = None,
        resources: ConnectionResources | None = None,
        lifecycle: DatasourceResourceLifecycle | None = None,
    ) -> None:
        self._vault = vault if vault is not None else get_credential_vault()
        self._resources = resources if resources is not None else ConnectionResources()
        self._lifecycle = (
            lifecycle if lifecycle is not None else get_datasource_resource_lifecycle()
        )

    def sqlite_path(self, profile: ConnectionProfile) -> Path:
        if profile.dialect != "sqlite":
            raise DataSourceConnectionError("The profile is not a SQLite datasource.")
        try:
            path = Path(profile.database_name).expanduser()
            path_stat = path.lstat()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise DataSourceConnectionError("SQLite database file is unavailable.") from exc
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise DataSourceConnectionError("SQLite database file is unavailable.")
        return path

    @contextmanager
    def sqlite_connection_scope(
        self,
        profile: ConnectionProfile,
        *,
        purpose: ConnectionPurpose,
        read_only: bool,
        timeout_seconds: float = 5,
        row_factory: Any | None = None,
    ) -> Generator[sqlite3.Connection, None, None]:
        """Open and deterministically close an embedded SQLite connection.

        ``purpose`` is intentionally part of the API even though SQLite has no
        SSH/TLS setup: callers must state the operation rather than opening a
        raw file path.  Query-like work uses SQLite URI read-only mode, which is
        a real authorization boundary rather than a convention at the caller.
        """

        del purpose
        path = self.sqlite_path(profile)
        try:
            if read_only:
                uri = path.resolve().as_uri() + "?mode=ro"
                connection = sqlite3.connect(uri, timeout=timeout_seconds, uri=True)
            else:
                connection = sqlite3.connect(str(path), timeout=timeout_seconds)
        except Exception as exc:
            raise DataSourceConnectionError("SQLite database connection could not be opened.") from exc
        if row_factory is not None:
            connection.row_factory = row_factory
        try:
            yield connection
        finally:
            connection.close()

    def duckdb_path(self, profile: ConnectionProfile) -> Path:
        """Return an existing, non-link DuckDB database file for safe read-only use.

        A persisted datasource must not use ``:memory:``: every new connection
        would create a distinct empty database and could make an authoritative
        schema sync erase a valid previous catalog.
        """
        if profile.dialect != "duckdb":
            raise DataSourceConnectionError("The profile is not a DuckDB datasource.")
        if profile.database_name.strip() == ":memory:":
            raise DataSourceConnectionError(
                "DuckDB :memory: is not permitted for persisted datasource operations."
            )
        try:
            path = Path(profile.database_name).expanduser()
            path_stat = path.lstat()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise DataSourceConnectionError("DuckDB database file is unavailable.") from exc
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise DataSourceConnectionError("DuckDB database file is unavailable.")
        return path

    @contextmanager
    def duckdb_connection_scope(
        self,
        profile: ConnectionProfile,
        *,
        purpose: ConnectionPurpose,
    ) -> Generator[Any, None, None]:
        """Open a read-only DuckDB connection without any network or vault access."""
        del purpose
        database_path = self.duckdb_path(profile)
        try:
            import duckdb

            connection = duckdb.connect(database=str(database_path), read_only=True)
        except Exception as exc:
            raise DataSourceConnectionError("DuckDB database connection could not be opened.") from exc
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def connection_scope(
        self,
        profile: ConnectionProfile,
        *,
        purpose: ConnectionPurpose,
        read_only: bool,
        pooled: bool = True,
        sqlite_row_factory: Any | None = None,
    ) -> Generator[Any, None, None]:
        """Open one database connection through the only credential boundary.

        Network passwords are resolved only after profile validation and while
        the resource scope is active.  SSH endpoint failures propagate as
        ``DataSourceConnectionError``; this method never retries a tunneled
        datasource against its direct host.  Managed network datasources use
        the shared pool, while transient connection tests always use a direct
        connection so a temporary tunnel cannot outlive its operation.
        """

        if profile.dialect == "sqlite":
            with self.sqlite_connection_scope(
                profile,
                purpose=purpose,
                read_only=read_only,
                row_factory=sqlite_row_factory,
            ) as connection:
                yield connection
            return

        if profile.dialect == "duckdb":
            if not read_only:
                raise DataSourceConnectionError(
                    "DuckDB write operations are not supported through the connection boundary."
                )
            with self.duckdb_connection_scope(profile, purpose=purpose) as connection:
                yield connection
            return

        # A non-managed profile may require a temporary SSH tunnel.  Pooling it
        # would retain a connection after that tunnel is stopped, so it is
        # deliberately not allowed for transient/test configuration.
        use_pool = pooled and profile.is_managed and purpose is not ConnectionPurpose.CONNECTION_TEST
        if use_pool:
            # Keep the lifecycle fence only for endpoint/pool checkout.  The
            # returned connection can finish its in-flight operation after an
            # update, but its disposed pool can never lend it to another run.
            with self._lifecycle.checkout(profile):
                with self._resources.endpoint_scope(profile, purpose) as endpoint:
                    connection_proxy = self._pooled_connection(profile, endpoint)
            connection = self._raw_connection(connection_proxy)
            close = connection_proxy.close
            read_only_started = False
            try:
                if read_only:
                    self._begin_read_only_transaction(profile, connection)
                    read_only_started = True
                yield connection
            finally:
                if read_only_started:
                    try:
                        connection.rollback()
                    except Exception:
                        # A failed query can already have aborted the
                        # transaction.  The connection must still be returned
                        # or closed below.
                        pass
                close()
            return

        # A temporary tunnel must remain open for the direct connection's
        # entire use.  Managed direct operations are intentionally fenced for
        # that same duration so a credential rotation cannot start a stale
        # direct connection between validation and driver creation.
        with self._lifecycle.checkout(profile):
            with self._driver_params_scope(profile, purpose=purpose) as params:
                connection = self._direct_connection(profile, params)
                read_only_started = False
                try:
                    if read_only:
                        self._begin_read_only_transaction(profile, connection)
                        read_only_started = True
                    yield connection
                finally:
                    if read_only_started:
                        try:
                            connection.rollback()
                        except Exception:
                            # A failed query can already have aborted the
                            # transaction.  The connection must still be returned
                            # or closed below.
                            pass
                    connection.close()

    @contextmanager
    def mysql_client_scope(
        self,
        profile: ConnectionProfile,
        *,
        purpose: ConnectionPurpose,
    ) -> Generator[MySQLClientInvocation, None, None]:
        """Resolve native MySQL-client inputs without exposing a params dict."""

        if profile.dialect != "mysql":
            raise DataSourceConnectionError("Native MySQL clients require a MySQL datasource.")
        with self._lifecycle.checkout(profile):
            with self._driver_params_scope(profile, purpose=purpose) as params:
                host = str(params["host"])
                port = int(params["port"])
                username = str(params["user"])
                database = str(params["database"])
                ssl_options = {
                    option: str(params[option])
                    for option in ("ssl_ca", "ssl_cert", "ssl_key")
                    if params.get(option)
                }
                yield MySQLClientInvocation(
                    host=host,
                    port=port,
                    username=username,
                    database=database,
                    _password=str(params["password"]),
                    ssl_options=ssl_options,
                )

    @contextmanager
    def _driver_params_scope(
        self,
        profile: ConnectionProfile,
        *,
        purpose: ConnectionPurpose,
    ) -> Generator[dict[str, Any], None, None]:
        if profile.dialect in {"sqlite", "duckdb"}:
            raise DataSourceConnectionError(
                f"{profile.dialect.title()} connections do not have network driver parameters."
            )
        with self._resources.endpoint_scope(profile, purpose) as endpoint:
            params = self._network_params(profile, endpoint)
            params["password"] = self._require_secret(
                profile.password_credential_id,
                CredentialKind.DATASOURCE_PASSWORD,
            )
            yield params

    @staticmethod
    def _network_params(
        profile: ConnectionProfile,
        endpoint: ConnectionEndpoint,
    ) -> dict[str, Any]:
        """Build driver metadata without resolving a password."""
        if profile.dialect == "mysql":
            params = {
                "host": endpoint.host,
                "port": endpoint.port,
                "user": profile.username,
                "database": profile.database_name,
                "charset": "utf8mb4",
                "cursorclass": pymysql.cursors.DictCursor,
                "connect_timeout": 5,
                "read_timeout": 10,
                "write_timeout": 10,
            }
            params.update(build_mysql_ssl_params(profile))
            return params

        if profile.dialect == "postgresql":
            params = {
                "host": endpoint.host,
                "port": endpoint.port,
                "user": profile.username,
                "database": profile.database_name,
            }
            params.update(build_postgres_ssl_params(profile))
            return params

        raise DataSourceConnectionError("Unsupported datasource dialect.")

    @staticmethod
    def _raw_connection(connection_proxy: Any) -> Any:
        return (
            getattr(connection_proxy, "dbapi_connection", None)
            or getattr(connection_proxy, "driver_connection", None)
            or getattr(connection_proxy, "connection", None)
            or connection_proxy
        )

    @staticmethod
    def _begin_read_only_transaction(profile: ConnectionProfile, connection: Any) -> None:
        cursor = connection.cursor()
        try:
            if profile.dialect == "mysql":
                cursor.execute("START TRANSACTION READ ONLY")
            elif profile.dialect == "postgresql":
                cursor.execute("BEGIN READ ONLY")
            else:
                raise DataSourceConnectionError("Read-only transactions require a network datasource.")
        finally:
            cursor.close()

    @staticmethod
    def _direct_connection(profile: ConnectionProfile, params: Mapping[str, Any]) -> Any:
        try:
            if profile.dialect == "mysql":
                return pymysql.connect(**dict(params))
            if profile.dialect == "postgresql":
                import psycopg2

                return psycopg2.connect(**dict(params), connect_timeout=5)
        except (DataSourceConnectionError, CredentialVaultUnavailableError):
            raise
        except Exception as exc:
            raise DataSourceConnectionError("Database connection could not be opened.") from exc
        raise DataSourceConnectionError("Unsupported datasource dialect.")

    def _pooled_connection(
        self,
        profile: ConnectionProfile,
        endpoint: ConnectionEndpoint,
    ) -> Any:
        from engine.connectivity._pools import (
            _get_mysql_pool,
            _get_postgres_pool,
            _ping_mysql_connection,
        )

        try:
            params = self._network_params(profile, endpoint)
            if profile.dialect == "mysql":
                connection_proxy = _get_mysql_pool(
                    profile,
                    host=endpoint.host,
                    port=endpoint.port,
                    params=params,
                    vault=self._vault,
                ).connect()
                _ping_mysql_connection(connection_proxy)
                return connection_proxy
            if profile.dialect == "postgresql":
                return _get_postgres_pool(
                    profile,
                    host=endpoint.host,
                    port=endpoint.port,
                    params=params,
                    vault=self._vault,
                ).connect()
        except (DataSourceConnectionError, CredentialVaultUnavailableError):
            raise
        except Exception as exc:
            # QueuePool can surface the raw DBAPI exception before the dialect
            # adapter sees it. Keep the sole connectivity boundary's error
            # contract identical for direct and pooled connections.
            raise DataSourceConnectionError("Database connection could not be opened.") from exc
        raise DataSourceConnectionError("Unsupported datasource dialect.")

    def _require_secret(self, credential_id: str | None, kind: CredentialKind) -> str:
        if not credential_id:
            raise DataSourceConnectionError(
                "A password credential is required for network datasource connections."
            )
        secret = self._vault.get(credential_id, expected_kind=kind)
        if not secret:
            raise DataSourceConnectionError(
                "Credential reference was not found or has the wrong kind."
            )
        return secret
