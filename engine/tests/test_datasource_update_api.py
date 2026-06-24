from fastapi.testclient import TestClient
import pytest

from engine.crypto import decrypt_password, encrypt_password
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DEFAULT_PROJECT_ID, DataSource, SchemaColumn, SchemaTable


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_datasource(db_session, *, password: str = "old-secret") -> DataSource:
    cipher, nonce = encrypt_password(password)
    ssh_cipher, ssh_nonce = encrypt_password("old-ssh")
    passphrase_cipher, passphrase_nonce = encrypt_password("old-passphrase")
    datasource = DataSource(
        id="update-ds",
        project_id=DEFAULT_PROJECT_ID,
        name="Old name",
        db_type="mysql",
        host="old.example.com",
        port=3306,
        database_name="old_db",
        username="old_user",
        password_ciphertext=cipher,
        password_nonce=nonce,
        ssh_enabled=True,
        ssh_host="old-bastion",
        ssh_port=22,
        ssh_username="old-ssh-user",
        ssh_password_ciphertext=ssh_cipher,
        ssh_password_nonce=ssh_nonce,
        ssh_pkey_path="C:/keys/old.pem",
        ssh_pkey_passphrase_ciphertext=passphrase_cipher,
        ssh_pkey_passphrase_nonce=passphrase_nonce,
        ssl_enabled=True,
        ssl_ca_path="C:/certs/old-ca.pem",
        ssl_cert_path="C:/certs/old-cert.pem",
        ssl_key_path="C:/certs/old-key.pem",
        ssl_verify_identity=True,
        connection_mode="direct",
        is_read_only=True,
        env="prod",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()
    return datasource


def _payload(**overrides):
    payload = {
        "name": "New name",
        "db_type": "mysql",
        "host": "new.example.com",
        "port": 3307,
        "database_name": "new_db",
        "username": "new_user",
        "password": "",
        "connection_mode": "direct",
        "is_read_only": False,
        "env": "test",
        "ssh_enabled": False,
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_username": "",
        "ssh_password": "",
        "ssh_pkey_path": "",
        "ssh_pkey_passphrase": "",
        "ssl_enabled": False,
        "ssl_ca_path": "",
        "ssl_cert_path": "",
        "ssl_key_path": "",
        "ssl_verify_identity": True,
    }
    payload.update(overrides)
    return payload


def test_update_datasource_updates_public_fields(client, db_session) -> None:
    datasource = _create_datasource(db_session)

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["name"] == "New name"
    assert body["host"] == "new.example.com"
    assert body["port"] == 3307
    assert body["database_name"] == "new_db"
    assert body["username"] == "new_user"
    assert body["is_read_only"] is False
    assert body["env"] == "test"
    assert body["ssh_enabled"] is False
    assert body["ssl_enabled"] is False

    db_session.refresh(datasource)
    assert datasource.name == "New name"
    assert datasource.host == "new.example.com"
    assert datasource.port == 3307


def test_update_datasource_preserves_blank_secrets(client, db_session) -> None:
    datasource = _create_datasource(db_session)
    old_password_cipher = datasource.password_ciphertext
    old_password_nonce = datasource.password_nonce
    old_ssh_cipher = datasource.ssh_password_ciphertext
    old_passphrase_cipher = datasource.ssh_pkey_passphrase_ciphertext

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    db_session.refresh(datasource)
    assert datasource.password_ciphertext == old_password_cipher
    assert datasource.password_nonce == old_password_nonce
    assert datasource.ssh_password_ciphertext == old_ssh_cipher
    assert datasource.ssh_pkey_passphrase_ciphertext == old_passphrase_cipher


def test_update_datasource_replaces_non_empty_secrets(client, db_session) -> None:
    datasource = _create_datasource(db_session)

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(
            password="new-secret",
            ssh_enabled=True,
            ssh_password="new-ssh",
            ssh_pkey_path="C:/keys/new.pem",
            ssh_pkey_passphrase="new-passphrase",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    db_session.refresh(datasource)
    assert decrypt_password(datasource.password_ciphertext, datasource.password_nonce) == "new-secret"
    assert decrypt_password(datasource.ssh_password_ciphertext, datasource.ssh_password_nonce) == "new-ssh"
    assert decrypt_password(datasource.ssh_pkey_passphrase_ciphertext, datasource.ssh_pkey_passphrase_nonce) == "new-passphrase"


def test_update_datasource_missing_id_returns_404(client) -> None:
    response = client.put(
        "/api/v1/datasources/missing",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_update_column_metadata_updates_semantic_fields(client, db_session) -> None:
    datasource = _create_datasource(db_session)
    table = SchemaTable(
        id="schema-table-1",
        data_source_id=datasource.id,
        table_schema="main",
        table_name="orders",
    )
    column = SchemaColumn(
        id="schema-column-1",
        table_id=table.id,
        column_name="total_amount",
        data_type="decimal",
        column_type="decimal(10,2)",
    )
    db_session.add_all([table, column])
    db_session.commit()

    response = client.put(
        f"/api/v1/schema/columns/{column.id}",
        json={
            "ai_description": "Order amount in base currency",
            "semantic_tags": "metric,revenue",
            "business_terms": "GMV",
            "ai_confidence": 0.92,
        },
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["success"] is True
    assert body["column"]["ai_description"] == "Order amount in base currency"
    assert body["column"]["semantic_tags"] == "metric,revenue"
    assert body["column"]["business_terms"] == "GMV"
    assert body["column"]["ai_confidence"] == 0.92

    db_session.refresh(column)
    assert column.ai_description == "Order amount in base currency"
