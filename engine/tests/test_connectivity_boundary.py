from __future__ import annotations

from dataclasses import FrozenInstanceError
import sqlite3
from types import SimpleNamespace

import pytest

from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.connectivity.resources import ConnectionResources
from engine.datasource import datasource_connection_dict
from engine.errors import DataSourceConnectionError
from engine.schemas.datasource import DataSourceTestRequest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def _network_config(password_credential_id: str, **extra: object) -> dict[str, object]:
    return {
        "id": "datasource-1",
        "connection_generation": 1,
        "db_type": "mysql",
        "host": "db.internal.test",
        "port": 3306,
        "database_name": "warehouse",
        "username": "readonly",
        "password_credential_id": password_credential_id,
        **extra,
    }


def test_profile_is_immutable_and_fingerprint_is_deterministic() -> None:
    profile = ConnectionProfile.from_mapping(
        _network_config("cred_datasource_password_opaque")
    )

    assert profile.fingerprint == ConnectionProfile.from_mapping(
        _network_config("cred_datasource_password_opaque")
    ).fingerprint
    assert profile.fingerprint.startswith("conn_")
    assert "opaque" not in profile.fingerprint

    with pytest.raises(FrozenInstanceError):
        profile.host = "other.internal.test"  # type: ignore[misc]


def test_profile_rejects_plaintext_credentials_at_the_boundary() -> None:
    with pytest.raises(DataSourceConnectionError, match="Plaintext credentials"):
        ConnectionProfile.from_mapping(
            _network_config(
                "cred_datasource_password_opaque",
                password="a-secret-that-must-not-cross-the-boundary",
            )
        )


def test_persisted_invalid_generation_is_not_normalized_to_one() -> None:
    datasource = SimpleNamespace(
        **_network_config("cred_datasource_password_opaque", connection_generation=0),
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
    )

    with pytest.raises(DataSourceConnectionError, match="positive integer"):
        ConnectionProfile.from_mapping(datasource_connection_dict(datasource))


def test_factory_resolves_network_password_only_from_vault() -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="vault-only-password",
    )
    profile = ConnectionProfile.from_mapping(_network_config(credential_id))

    with ConnectionFactory(vault=vault).mysql_client_scope(
        profile,
        purpose=ConnectionPurpose.BACKUP,
    ) as client:
        assert client.environment()["MYSQL_PWD"] == "vault-only-password"
        assert client.host == "db.internal.test"
        assert client.database == "warehouse"


def test_connection_test_configuration_keeps_credential_references_opaque(monkeypatch) -> None:
    from engine.api.datasources import crud

    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="never-placed-in-the-config-dict",
    )
    monkeypatch.setattr(crud, "get_credential_vault", lambda: vault)

    config = crud._connection_test_config(
        DataSourceTestRequest(
            db_type="mysql",
            host="db.internal.test",
            port=3306,
            database_name="warehouse",
            username="readonly",
            password_credential_id=credential_id,
        )
    )

    assert config["password_credential_id"] == credential_id
    assert "password" not in config
    assert "ssh_password" not in config


def test_sqlite_profile_uses_file_path_without_network_credentials(tmp_path) -> None:
    sqlite_path = tmp_path / "warehouse.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")

    profile = ConnectionProfile.from_mapping(
        {"db_type": "sqlite", "database_name": str(sqlite_path)}
    )

    assert ConnectionFactory(vault=InMemoryCredentialVault()).sqlite_path(profile) == sqlite_path


def test_duckdb_profile_uses_an_existing_regular_file_without_vault_access(tmp_path) -> None:
    duckdb = pytest.importorskip("duckdb")
    database_path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute("CREATE TABLE orders (id INTEGER)")

    class NoVault:
        def get(self, *_args, **_kwargs):
            raise AssertionError("DuckDB must not access the credential vault")

    profile = ConnectionProfile.from_mapping(
        {"db_type": "duckdb", "database_name": str(database_path)}
    )
    factory = ConnectionFactory(vault=NoVault())

    assert factory.duckdb_path(profile) == database_path
    with factory.duckdb_connection_scope(profile, purpose=ConnectionPurpose.SCHEMA_SYNC) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_duckdb_memory_and_non_regular_paths_are_rejected_for_persisted_operations(tmp_path) -> None:
    factory = ConnectionFactory(vault=InMemoryCredentialVault())
    memory_profile = ConnectionProfile.from_mapping(
        {"db_type": "duckdb", "database_name": ":memory:"}
    )
    directory_profile = ConnectionProfile.from_mapping(
        {"db_type": "duckdb", "database_name": str(tmp_path)}
    )

    with pytest.raises(DataSourceConnectionError, match=":memory:"):
        factory.duckdb_path(memory_profile)
    with pytest.raises(DataSourceConnectionError, match="unavailable"):
        factory.duckdb_path(directory_profile)


def test_duckdb_symlink_is_not_accepted_as_a_persisted_database_file(tmp_path) -> None:
    database_path = tmp_path / "warehouse.duckdb"
    database_path.write_bytes(b"not inspected; only the file boundary matters")
    symlink_path = tmp_path / "warehouse-link.duckdb"
    try:
        symlink_path.symlink_to(database_path)
    except OSError:
        pytest.skip("Creating symbolic links is unavailable on this host.")

    profile = ConnectionProfile.from_mapping(
        {"db_type": "duckdb", "database_name": str(symlink_path)}
    )

    with pytest.raises(DataSourceConnectionError, match="unavailable"):
        ConnectionFactory(vault=InMemoryCredentialVault()).duckdb_path(profile)


def test_ssh_tunnel_failure_never_falls_back_to_direct_host() -> None:
    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="database-password",
    )
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="jumpbox-password",
    )
    profile = ConnectionProfile.from_mapping(
        _network_config(
            password_credential_id,
            ssh_enabled=True,
            ssh_host="jump.internal.test",
            ssh_port=22,
            ssh_username="jump-user",
            ssh_password_credential_id=ssh_password_credential_id,
        )
    )
    tunnel_configs: list[dict[str, object]] = []

    def fail_tunnel(config: dict[str, object]) -> object:
        tunnel_configs.append(config)
        raise RuntimeError("jumpbox-password must never be exposed")

    resources = ConnectionResources(temporary_tunnel_opener=fail_tunnel)
    factory = ConnectionFactory(vault=vault, resources=resources)

    with pytest.raises(DataSourceConnectionError) as exc_info:
        with factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.CONNECTION_TEST,
            read_only=False,
            pooled=False,
        ):
            pytest.fail("A failed SSH tunnel must not fall back to the datasource host.")

    assert "jumpbox-password" not in str(exc_info.value)
    assert len(tunnel_configs) == 1
    assert tunnel_configs[0]["host"] == "db.internal.test"
    assert "password" not in tunnel_configs[0]
    assert "ssh_password" not in tunnel_configs[0]


def test_pooled_connection_error_never_leaks_driver_message(monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="database-password",
    )
    profile = ConnectionProfile.from_mapping(
        _network_config(password_credential_id, is_managed=True)
    )
    sentinel = "pooled-driver-password-sentinel"

    class FailingPool:
        def connect(self) -> object:
            raise RuntimeError(f"driver failed with password={sentinel}")

    monkeypatch.setattr(
        "engine.connectivity._pools._get_mysql_pool",
        lambda *_args, **_kwargs: FailingPool(),
    )
    factory = ConnectionFactory(vault=vault)

    with pytest.raises(DataSourceConnectionError) as exc_info:
        with factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.QUERY,
            read_only=True,
        ):
            pytest.fail("A failed pool checkout must not yield a connection.")

    assert sentinel not in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_invalid_temporary_tunnel_endpoint_is_closed_before_failing() -> None:
    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="database-password",
    )
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="jumpbox-password",
    )
    profile = ConnectionProfile.from_mapping(
        _network_config(
            password_credential_id,
            ssh_enabled=True,
            ssh_host="jump.internal.test",
            ssh_username="jump-user",
            ssh_password_credential_id=ssh_password_credential_id,
        )
    )

    class InvalidTunnel:
        local_bind_port = None
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    tunnel = InvalidTunnel()
    factory = ConnectionFactory(
        vault=vault,
        resources=ConnectionResources(temporary_tunnel_opener=lambda _config: tunnel),
    )

    with pytest.raises(DataSourceConnectionError):
        with factory.connection_scope(
            profile,
            purpose=ConnectionPurpose.CONNECTION_TEST,
            read_only=False,
            pooled=False,
        ):
            pytest.fail("Invalid tunnel endpoints must not expose a direct connection.")

    assert tunnel.stopped is True
