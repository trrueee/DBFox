from pathlib import Path

import pytest

from engine.datasource import build_postgres_ssl_params, test_connection
from engine.errors import DataSourceConnectionError


def test_sqlite_connection_test_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(DataSourceConnectionError):
        test_connection({"db_type": "sqlite", "database_name": str(missing)})

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
