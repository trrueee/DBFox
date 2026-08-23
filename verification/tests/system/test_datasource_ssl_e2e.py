import os
from pathlib import Path

import pytest
import engine.datasource as datasource_module
from engine.datasource import test_connection as run_test_connection
from engine.errors import DataSourceConnectionError
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault

@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.slow
def test_mysql_ssl_connection_e2e(monkeypatch) -> None:
    if os.getenv("DBFOX_RUN_MYSQL_SSL_E2E") != "1":
        pytest.skip("set DBFOX_RUN_MYSQL_SSL_E2E=1 with the documented isolated fixture")
    required = {
        name: os.getenv(name, "").strip()
        for name in (
            "DBFOX_MYSQL_SSL_HOST",
            "DBFOX_MYSQL_SSL_PORT",
            "DBFOX_MYSQL_SSL_DATABASE",
            "DBFOX_MYSQL_SSL_USER",
            "DBFOX_MYSQL_SSL_PASSWORD",
            "DBFOX_MYSQL_SSL_CA_PATH",
        )
    }
    missing = [name for name, value in required.items() if not value]
    assert not missing, f"missing opted-in MySQL SSL fixture settings: {missing}"
    ca_path = Path(required["DBFOX_MYSQL_SSL_CA_PATH"]).resolve(strict=True)

    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret=required["DBFOX_MYSQL_SSL_PASSWORD"],
    )
    monkeypatch.setattr(datasource_module, "get_credential_vault", lambda: vault)

    # 1. Verify Non-SSL connection triggers connection error under REQUIRE SSL policy
    config_no_ssl = {
        "host": required["DBFOX_MYSQL_SSL_HOST"],
        "port": int(required["DBFOX_MYSQL_SSL_PORT"]),
        "database_name": required["DBFOX_MYSQL_SSL_DATABASE"],
        "username": required["DBFOX_MYSQL_SSL_USER"],
        "password_credential_id": password_credential_id,
        "ssl_enabled": False,
    }
    
    with pytest.raises(DataSourceConnectionError) as exc_info:
        run_test_connection(config_no_ssl)
    assert "无法建立数据库连接" in str(exc_info.value) or "Access denied" in str(exc_info.value)

    # 2. Verify CA-enabled connection establishes successfully, registers tables count, and marks user as readonly
    config_ssl = {
        "host": required["DBFOX_MYSQL_SSL_HOST"],
        "port": int(required["DBFOX_MYSQL_SSL_PORT"]),
        "database_name": required["DBFOX_MYSQL_SSL_DATABASE"],
        "username": required["DBFOX_MYSQL_SSL_USER"],
        "password_credential_id": password_credential_id,
        "ssl_enabled": True,
        "ssl_ca_path": str(ca_path),
        "ssl_verify_identity": True,
    }

    res = run_test_connection(config_ssl)
    assert res["ok"] is True
    assert res["tablesCount"] == 1
    assert res["readonly"] is True
