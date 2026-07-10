from pathlib import Path

import pytest

from engine.datasource import build_postgres_ssl_params, test_connection as run_test_connection
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def test_sqlite_connection_test_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(DataSourceConnectionError):
        run_test_connection({"db_type": "sqlite", "database_name": str(missing)})

    assert not missing.exists()


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

    with patch("pymysql.connect") as mock_connect:
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
            "password": "pwd",
            "ssh_enabled": True,
            "ssh_host": "jump",
            "ssh_port": 22,
            "ssh_username": "sshuser",
            "ssh_password": "sshpwd",
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
                "password": "pwd",
                "ssh_enabled": True,
                "ssh_host": "jump",
                "ssh_port": 22,
                "ssh_username": "sshuser",
                "ssh_password": "sshpwd",
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

    with patch("pymysql.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [("8.0.25",), (10,), ("GRANT ALL PRIVILEGES ON *.* TO 'user'@'%'",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        config = {
            "id": "ds_123",
            "is_managed": True,
            "db_type": "mysql",
            "host": "localhost",
            "port": 3306,
            "database_name": "testdb",
            "username": "user",
            "password": "pwd",
            "ssh_enabled": True,
            "ssh_host": "jump",
            "ssh_port": 22,
            "ssh_username": "sshuser",
            "ssh_password_credential_id": ssh_password_credential_id,
        }

        with patch("engine.tunnel.get_credential_vault", return_value=vault):
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

