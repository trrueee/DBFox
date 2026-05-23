import pytest

from engine.crypto import encrypt_password
from engine.datasource import build_mysql_ssl_params, get_mysql_connection_params
from engine.errors import DataSourceConnectionError


def test_build_mysql_ssl_params_disabled() -> None:
    assert build_mysql_ssl_params({"ssl_enabled": False}) == {}


def test_build_mysql_ssl_params_requires_ca_for_identity_verification() -> None:
    with pytest.raises(DataSourceConnectionError):
        build_mysql_ssl_params(
            {
                "ssl_enabled": True,
                "ssl_verify_identity": True,
                "ssl_ca_path": "",
            }
        )


def test_build_mysql_ssl_params_includes_certificate_paths() -> None:
    params = build_mysql_ssl_params(
        {
            "ssl_enabled": True,
            "ssl_ca_path": "C:/certs/mysql-ca.pem",
            "ssl_cert_path": "C:/certs/client-cert.pem",
            "ssl_key_path": "C:/certs/client-key.pem",
            "ssl_verify_identity": True,
        }
    )

    assert params == {
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
        "ssl_ca": "C:/certs/mysql-ca.pem",
        "ssl_cert": "C:/certs/client-cert.pem",
        "ssl_key": "C:/certs/client-key.pem",
    }


def test_build_mysql_ssl_params_can_disable_hostname_verification_explicitly() -> None:
    params = build_mysql_ssl_params(
        {
            "ssl_enabled": True,
            "ssl_verify_identity": False,
        }
    )

    assert params["ssl_verify_cert"] is True
    assert params["ssl_verify_identity"] is False
    assert "ssl_ca" not in params


def test_get_mysql_connection_params_passes_ssl_options() -> None:
    cipher, nonce = encrypt_password("secret")

    params = get_mysql_connection_params(
        {
            "host": "db.example.com",
            "port": 3306,
            "username": "readonly",
            "database_name": "analytics",
            "password_ciphertext": cipher,
            "password_nonce": nonce,
            "ssl_enabled": True,
            "ssl_ca_path": "C:/certs/mysql-ca.pem",
            "ssl_cert_path": "C:/certs/client-cert.pem",
            "ssl_key_path": "C:/certs/client-key.pem",
            "ssl_verify_identity": True,
        }
    )

    assert params["ssl_verify_cert"] is True
    assert params["ssl_verify_identity"] is True
    assert params["ssl_ca"] == "C:/certs/mysql-ca.pem"
    assert params["ssl_cert"] == "C:/certs/client-cert.pem"
    assert params["ssl_key"] == "C:/certs/client-key.pem"
    assert params["password"] == "secret"
