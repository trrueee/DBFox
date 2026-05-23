import pytest
import os
import socket
from engine.datasource import test_connection as run_test_connection
from engine.errors import DataSourceConnectionError

def test_mysql_ssl_connection_e2e() -> None:
    # Probe if the local test container on port 3308 is up and listening
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 3308))
        docker_available = True
    except Exception:
        docker_available = False
    finally:
        s.close()

    if not docker_available:
        pytest.skip("Docker MySQL SSL test container is not active on port 3308.")

    # 1. Verify Non-SSL connection triggers connection error under REQUIRE SSL policy
    config_no_ssl = {
        "host": "127.0.0.1",
        "port": 3308,
        "database_name": "databox_ssl",
        "username": "databox_readonly",
        "password": "readonly_pass",
        "ssl_enabled": False,
    }
    
    with pytest.raises(DataSourceConnectionError) as exc_info:
        run_test_connection(config_no_ssl)
    assert "无法建立数据库连接" in str(exc_info.value) or "Access denied" in str(exc_info.value)

    # 2. Verify CA-enabled connection establishes successfully, registers tables count, and marks user as readonly
    ca_path = os.path.abspath(r"d:\Project\DataBox\databox-mysql-ssl-test\certs\ca.pem")
    config_ssl = {
        "host": "127.0.0.1",
        "port": 3308,
        "database_name": "databox_ssl",
        "username": "databox_readonly",
        "password": "readonly_pass",
        "ssl_enabled": True,
        "ssl_ca_path": ca_path,
        "ssl_verify_identity": True,
    }

    res = run_test_connection(config_ssl)
    assert res["ok"] is True
    assert res["tablesCount"] == 1
    assert res["readonly"] is True
