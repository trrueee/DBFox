import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import HTTPException

import engine.connectivity.resources as connectivity_resources_module
import engine.datasource as datasource_module
import engine.tunnel as tunnel_module
from engine.datasource import build_postgres_ssl_params, test_connection as run_test_connection
from engine.connectivity.profile import ConnectionProfile
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


@contextmanager
def _capture_module_logger(monkeypatch, caplog, module, level: int):
    """Inject an unregistered logger so this test does not alter app logging."""
    capture_logger = logging.Logger(f"test.{module.__name__}.boundary")
    capture_logger.setLevel(level)
    capture_logger.propagate = False
    capture_logger.addHandler(caplog.handler)
    try:
        with monkeypatch.context() as scoped_monkeypatch:
            scoped_monkeypatch.setattr(module, "logger", capture_logger)
            yield
    finally:
        capture_logger.removeHandler(caplog.handler)


def _vault_password(monkeypatch, secret: str) -> tuple[InMemoryCredentialVault, str]:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.DATASOURCE_PASSWORD, secret=secret)
    monkeypatch.setattr(datasource_module, "get_credential_vault", lambda: vault)
    return vault, credential_id


def test_sqlite_connection_test_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(DataSourceConnectionError):
        run_test_connection({"db_type": "sqlite", "database_name": str(missing)})

    assert not missing.exists()


def test_sqlite_connection_error_never_leaks_driver_exception(tmp_path: Path, monkeypatch, caplog) -> None:
    sentinel = "sqlite-connection-secret-sentinel"
    database_path = tmp_path / "existing.sqlite"
    database_path.touch()

    def fail_connect(*_args, **_kwargs):
        raise RuntimeError(f"SQLite driver failed with password={sentinel}")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)

    with _capture_module_logger(monkeypatch, caplog, datasource_module, logging.WARNING):
        with pytest.raises(DataSourceConnectionError) as exc_info:
            run_test_connection({"db_type": "sqlite", "database_name": str(database_path)})

    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_mysql_connection_error_never_leaks_driver_exception(monkeypatch, caplog) -> None:
    sentinel = "mysql-connection-secret-sentinel"
    _vault, password_credential_id = _vault_password(monkeypatch, sentinel)

    def fail_connect(**_kwargs):
        raise RuntimeError(f"MySQL driver failed with password={sentinel}")

    monkeypatch.setattr("engine.connectivity.factory.pymysql.connect", fail_connect)

    with _capture_module_logger(monkeypatch, caplog, datasource_module, logging.WARNING):
        with pytest.raises(DataSourceConnectionError) as exc_info:
            run_test_connection({
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database_name": "dbfox",
                "username": "dbfox",
                "password_credential_id": password_credential_id,
            })

    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_mysql_connection_test_accepts_dict_cursor_rows(monkeypatch) -> None:
    from unittest.mock import MagicMock

    _vault, password_credential_id = _vault_password(monkeypatch, "test-password")
    connection = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"VERSION()": "5.7.24"},
        {"COUNT(*)": 50},
    ]
    cursor.fetchall.return_value = [
        {"Grants for creatorhub@%": "GRANT SELECT ON `creatorhub`.* TO 'creatorhub'@'%'"}
    ]
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr("engine.connectivity.factory.pymysql.connect", lambda **_kwargs: connection)

    result = run_test_connection({
        "db_type": "mysql",
        "host": "localhost",
        "port": 3306,
        "database_name": "creatorhub",
        "username": "creatorhub",
        "password_credential_id": password_credential_id,
    })

    assert result["ok"] is True
    assert result["serverVersion"] == "5.7.24"
    assert result["tablesCount"] == 50
    assert result["readonly"] is True


def test_duckdb_connection_failure_uses_its_own_safe_log_operation(monkeypatch, caplog) -> None:
    class FailingFactory:
        @contextmanager
        def connection_scope(self, *_args, **_kwargs):
            raise RuntimeError("DuckDB connection failed")
            yield None

    profile = ConnectionProfile.from_mapping({"db_type": "duckdb", "database_name": ":memory:"})

    with _capture_module_logger(monkeypatch, caplog, datasource_module, logging.WARNING):
        with pytest.raises(DataSourceConnectionError):
            datasource_module._test_duckdb_connection(profile, FailingFactory())

    assert "datasource_test_duckdb_connection" in caplog.text


def test_postgres_connection_error_never_leaks_driver_exception(monkeypatch, caplog) -> None:
    psycopg2 = pytest.importorskip("psycopg2")
    sentinel = "postgres-connection-secret-sentinel"
    _vault, password_credential_id = _vault_password(monkeypatch, sentinel)

    def fail_connect(**_kwargs):
        raise RuntimeError(f"PostgreSQL driver failed with password={sentinel}")

    monkeypatch.setattr(psycopg2, "connect", fail_connect)

    with _capture_module_logger(monkeypatch, caplog, datasource_module, logging.WARNING):
        with pytest.raises(DataSourceConnectionError) as exc_info:
            run_test_connection({
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database_name": "dbfox",
                "username": "dbfox",
                "password_credential_id": password_credential_id,
            })

    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_temporary_tunnel_error_never_leaks_tunnel_exception(monkeypatch, caplog) -> None:
    sentinel = "tunnel-connection-secret-sentinel"
    vault, password_credential_id = _vault_password(monkeypatch, "not-logged")
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="ssh-not-logged",
    )

    def fail_open_tunnel(_config):
        raise RuntimeError(f"SSH password={sentinel}")

    monkeypatch.setattr(
        connectivity_resources_module,
        "open_temporary_tunnel",
        fail_open_tunnel,
    )

    with _capture_module_logger(
        monkeypatch,
        caplog,
        connectivity_resources_module,
        logging.WARNING,
    ):
        with pytest.raises(DataSourceConnectionError) as exc_info:
            run_test_connection({
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database_name": "dbfox",
                "username": "dbfox",
                "password_credential_id": password_credential_id,
                "ssh_enabled": True,
                "ssh_host": "jump.example.test",
                "ssh_username": "jump-user",
                "ssh_password_credential_id": ssh_password_credential_id,
            })

    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_managed_tunnel_reconnect_error_never_persists_exception_text(monkeypatch, caplog) -> None:
    sentinel = "managed-tunnel-secret-sentinel"
    manager = tunnel_module.TunnelManager()
    old_tunnel = MagicMock()
    old_tunnel.is_active = False
    resource_key = ("ds-managed-tunnel", 1, "conn-managed-tunnel")
    instance = tunnel_module.TunnelInstance(
        resource_key,
        {
            "id": "ds-managed-tunnel",
            "connection_generation": 1,
            "connection_fingerprint": "conn-managed-tunnel",
        },
        old_tunnel,
    )
    manager._tunnels[resource_key] = instance

    def fail_start(_config):
        raise RuntimeError(f"SSH key passphrase={sentinel}")

    monkeypatch.setattr(manager, "health_check", lambda _resource_key: False)
    monkeypatch.setattr(manager, "_start_physical_tunnel", fail_start)

    with _capture_module_logger(monkeypatch, caplog, tunnel_module, logging.ERROR):
        with pytest.raises(DataSourceConnectionError) as exc_info:
            manager.get_or_reconnect(
                {
                    "id": "ds-managed-tunnel",
                    "connection_generation": 1,
                    "connection_fingerprint": "conn-managed-tunnel",
                }
            )

    assert instance.state == tunnel_module.TunnelState.FAILED
    assert instance.error_message == "SSH tunnel reconnection failed."
    assert sentinel not in str(exc_info.value)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_release_datasource_pool_error_never_leaks_exception_text(monkeypatch, caplog) -> None:
    from engine.api.datasources import crud as datasource_crud

    sentinel = "datasource-pool-release-secret-sentinel"

    class FailingPoolRegistry:
        def dispose_datasource(self, _datasource_id):
            raise RuntimeError(f"pool cleanup password={sentinel}")

    monkeypatch.setattr(
        "engine.sql.pool_registry.get_pool_registry",
        lambda: FailingPoolRegistry(),
    )

    with _capture_module_logger(monkeypatch, caplog, datasource_crud, logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            datasource_crud.api_release_datasource("ds-pool", object())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "DATASOURCE_POOL_RELEASE_FAILED",
        "message": "Datasource connection pool could not be released.",
    }
    assert sentinel not in repr(exc_info.value.detail)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_postgres_ssl_verify_full_requires_ca() -> None:
    with pytest.raises(DataSourceConnectionError):
        build_postgres_ssl_params({"ssl_enabled": True, "ssl_verify_identity": True})


def test_postgres_ssl_params_map_shared_fields() -> None:
    params = build_postgres_ssl_params({
        "ssl_enabled": True,
        "ssl_verify_identity": True,
        "ssl_ca_path": "ca.pem",
        "ssl_cert_path": "client.crt",
        "ssl_key_path": "client.key",
    })

    assert params == {
        "sslmode": "verify-full",
        "sslrootcert": "ca.pem",
        "sslcert": "client.crt",
        "sslkey": "client.key",
    }


from unittest.mock import MagicMock, patch
from engine.datasource import TUNNEL_MANAGER, get_or_create_tunnel_for_dict, open_temporary_tunnel

@patch("engine.tunnel.SSHTunnelForwarder")
def test_temporary_tunnel_stops_on_success_and_failure(mock_tunnel_class) -> None:
    mock_tunnel = MagicMock()
    mock_tunnel.local_bind_port = 12345
    mock_tunnel_class.return_value = mock_tunnel
    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="pwd",
    )
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="sshpwd",
    )

    with (
        patch("pymysql.connect") as mock_connect,
        patch("engine.datasource.get_credential_vault", return_value=vault),
        patch("engine.tunnel.get_credential_vault", return_value=vault),
    ):
        # Success case
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [("8.0.25",), (10,), ("GRANT ALL PRIVILEGES ON *.* TO 'user'@'%'",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        res = run_test_connection({
            "db_type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database_name": "testdb",
            "username": "user",
            "password_credential_id": password_credential_id,
            "ssh_enabled": True,
            "ssh_host": "jump",
            "ssh_port": 22,
            "ssh_username": "sshuser",
            "ssh_password_credential_id": ssh_password_credential_id,
        })
        assert res["ok"] is True
        mock_tunnel.start.assert_called_once()
        mock_tunnel.stop.assert_called_once()

        mock_tunnel.reset_mock()
        mock_connect.reset_mock()

        # Failure case
        mock_connect.side_effect = Exception("db connect error")
        with pytest.raises(DataSourceConnectionError):
            run_test_connection({
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database_name": "testdb",
                "username": "user",
                "password_credential_id": password_credential_id,
                "ssh_enabled": True,
                "ssh_host": "jump",
                "ssh_port": 22,
                "ssh_username": "sshuser",
                "ssh_password_credential_id": ssh_password_credential_id,
            })
        mock_tunnel.start.assert_called_once()
        mock_tunnel.stop.assert_called_once()


@patch("engine.tunnel.SSHTunnelForwarder")
def test_managed_tunnel_does_not_stop_on_test_connection(mock_tunnel_class) -> None:
    mock_tunnel = MagicMock()
    mock_tunnel.local_bind_port = 12345
    mock_tunnel.is_active = True
    mock_tunnel_class.return_value = mock_tunnel
    vault = InMemoryCredentialVault()
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="ssh-password",
    )
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="pwd",
    )

    with patch("pymysql.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [("8.0.25",), (10,), ("GRANT ALL PRIVILEGES ON *.* TO 'user'@'%'",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        config = {
            "id": "ds_123",
            "is_managed": True,
            "connection_generation": 1,
            "db_type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database_name": "testdb",
            "username": "user",
            "password_credential_id": password_credential_id,
            "ssh_enabled": True,
            "ssh_host": "jump",
            "ssh_port": 22,
            "ssh_username": "sshuser",
            "ssh_password_credential_id": ssh_password_credential_id,
        }

        with (
            patch("engine.datasource.get_credential_vault", return_value=vault),
            patch("engine.tunnel.get_credential_vault", return_value=vault),
        ):
            res = run_test_connection(config)
            assert res["ok"] is True
            mock_tunnel.start.assert_called_once()
            mock_tunnel.stop.assert_not_called()
            
            TUNNEL_MANAGER.close_tunnel("ds_123")
            mock_tunnel.stop.assert_called_once()


@patch("engine.tunnel.TUNNEL_MANAGER")
def test_close_active_tunnel_calls_manager(mock_manager) -> None:
    from engine.datasource import close_active_tunnel
    close_active_tunnel("some_id")
    mock_manager.close_tunnel.assert_called_once_with("some_id")

