import json
import pytest
from unittest.mock import MagicMock

from engine.api.agent import sse_failed_event
from engine.datasource import datasource_connection_dict
from engine.projects.service import resolve_project_id, get_or_create_default_project, Project
from engine.models import DEFAULT_PROJECT_ID


def test_sse_failed_event() -> None:
    event_str = sse_failed_event("evt_123", "run_456", "Test error message", "ERR_CODE")
    assert event_str.startswith("event: agent.run.failed\n")
    
    lines = event_str.strip().split("\n")
    assert len(lines) >= 2
    assert lines[0] == "event: agent.run.failed"
    assert lines[1].startswith("data: ")
    
    data_json = lines[1][6:]
    payload = json.loads(data_json)
    assert payload["event_id"] == "evt_123"
    assert payload["run_id"] == "run_456"
    assert payload["error"] == "Test error message"
    assert payload["code"] == "ERR_CODE"
    assert payload["type"] == "agent.run.failed"


def test_datasource_connection_dict() -> None:
    mock_ds = MagicMock()
    mock_ds.id = "ds_123"
    mock_ds.host = "localhost"
    mock_ds.port = 3306
    mock_ds.username = "root"
    mock_ds.database_name = "testdb"
    mock_ds.password_ciphertext = "pass_cipher"
    mock_ds.password_nonce = "pass_nonce"
    mock_ds.ssh_enabled = True
    mock_ds.ssh_host = "jump"
    mock_ds.ssh_port = 22
    mock_ds.ssh_username = "sshuser"
    mock_ds.ssh_password_ciphertext = "ssh_pass_cipher"
    mock_ds.ssh_password_nonce = "ssh_pass_nonce"
    mock_ds.ssh_pkey_path = "/path/to/key"
    mock_ds.ssh_pkey_passphrase_ciphertext = "pkey_cipher"
    mock_ds.ssh_pkey_passphrase_nonce = "pkey_nonce"
    mock_ds.ssl_enabled = True
    mock_ds.ssl_ca_path = "/path/to/ca"
    mock_ds.ssl_cert_path = "/path/to/cert"
    mock_ds.ssl_key_path = "/path/to/key"
    mock_ds.ssl_verify_identity = True

    config = datasource_connection_dict(mock_ds)
    assert config["id"] == "ds_123"
    assert config["host"] == "localhost"
    assert config["port"] == 3306
    assert config["username"] == "root"
    assert config["database_name"] == "testdb"
    assert config["password_ciphertext"] == "pass_cipher"
    assert config["password_nonce"] == "pass_nonce"
    assert config["ssh_enabled"] is True
    assert config["ssh_host"] == "jump"
    assert config["ssh_port"] == 22
    assert config["ssh_username"] == "sshuser"
    assert config["ssh_password_ciphertext"] == "ssh_pass_cipher"
    assert config["ssh_password_nonce"] == "ssh_pass_nonce"
    assert config["ssh_pkey_path"] == "/path/to/key"
    assert config["ssh_pkey_passphrase_ciphertext"] == "pkey_cipher"
    assert config["ssh_pkey_passphrase_nonce"] == "pkey_nonce"
    assert config["ssl_enabled"] is True
    assert config["ssl_ca_path"] == "/path/to/ca"
    assert config["ssl_cert_path"] == "/path/to/cert"
    assert config["ssl_key_path"] == "/path/to/key"
    assert config["ssl_verify_identity"] is True


def test_project_id_resolution_fallback(db_session) -> None:
    # Test fallback to default project when project_id is None or empty or DEFAULT_PROJECT_ID
    pid1 = resolve_project_id(db_session, None)
    pid2 = resolve_project_id(db_session, "")
    pid3 = resolve_project_id(db_session, DEFAULT_PROJECT_ID)
    
    assert pid1 == DEFAULT_PROJECT_ID
    assert pid2 == DEFAULT_PROJECT_ID
    assert pid3 == DEFAULT_PROJECT_ID
    
    # Verify default project actually exists in db
    proj = db_session.query(Project).filter(Project.id == DEFAULT_PROJECT_ID).first()
    assert proj is not None
    assert proj.status == "active"
