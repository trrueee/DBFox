from fastapi.testclient import TestClient
import pytest

from engine.api.credentials import get_credential_lease_registry
from engine.api.datasources import crud as datasource_crud
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DEFAULT_PROJECT_ID, DataSource, Project, SchemaColumn, SchemaTable
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


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


@pytest.fixture
def credential_vault(monkeypatch) -> InMemoryCredentialVault:
    vault = InMemoryCredentialVault()
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    return vault


def _create_datasource(db_session, vault: InMemoryCredentialVault) -> DataSource:
    if db_session.get(Project, DEFAULT_PROJECT_ID) is None:
        db_session.add(
            Project(
                id=DEFAULT_PROJECT_ID,
                name="Datasource update API test project",
                description="Project required by the datasource foreign key.",
            )
        )
        db_session.flush()

    datasource = DataSource(
        id="update-ds",
        project_id=DEFAULT_PROJECT_ID,
        name="Old name",
        db_type="mysql",
        host="old.example.com",
        port=3306,
        database_name="old_db",
        username="old_user",
        password_credential_id=vault.put(
            kind=CredentialKind.DATASOURCE_PASSWORD,
            secret="old-secret",
        ),
        ssh_enabled=True,
        ssh_host="old-bastion",
        ssh_port=22,
        ssh_username="old-ssh-user",
        ssh_password_credential_id=vault.put(
            kind=CredentialKind.SSH_PASSWORD,
            secret="old-ssh",
        ),
        ssh_pkey_path="C:/keys/old.pem",
        ssh_key_passphrase_credential_id=vault.put(
            kind=CredentialKind.SSH_KEY_PASSPHRASE,
            secret="old-passphrase",
        ),
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
        "connection_mode": "direct",
        "is_read_only": False,
        "env": "test",
        "ssh_enabled": False,
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_username": "",
        "ssh_pkey_path": "",
        "ssl_enabled": False,
        "ssl_ca_path": "",
        "ssl_cert_path": "",
        "ssl_key_path": "",
        "ssl_verify_identity": True,
    }
    payload.update(overrides)
    return payload


def test_update_datasource_updates_public_fields(client, db_session, credential_vault) -> None:
    datasource = _create_datasource(db_session, credential_vault)

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


def test_update_datasource_disabling_ssh_removes_stale_ssh_credential_references(
    client,
    db_session,
    credential_vault,
) -> None:
    datasource = _create_datasource(db_session, credential_vault)
    old_password_credential_id = datasource.password_credential_id
    old_ssh_password_credential_id = datasource.ssh_password_credential_id
    old_ssh_key_passphrase_credential_id = datasource.ssh_key_passphrase_credential_id

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    db_session.refresh(datasource)
    assert datasource.password_credential_id == old_password_credential_id
    assert datasource.ssh_password_credential_id is None
    assert datasource.ssh_key_passphrase_credential_id is None
    assert old_ssh_password_credential_id is not None
    assert old_ssh_key_passphrase_credential_id is not None
    assert credential_vault.get(old_ssh_password_credential_id) is None
    assert credential_vault.get(old_ssh_key_passphrase_credential_id) is None


def test_update_datasource_replaces_credential_references(client, db_session, credential_vault) -> None:
    datasource = _create_datasource(db_session, credential_vault)
    old_credential_ids = {
        datasource.password_credential_id,
        datasource.ssh_password_credential_id,
        datasource.ssh_key_passphrase_credential_id,
    }
    new_password_secret = "new-datasource-secret"
    new_ssh_password_secret = "new-ssh-password-secret"
    new_ssh_key_passphrase_secret = "new-ssh-key-passphrase-secret"
    new_password_credential_id = credential_vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret=new_password_secret,
    )
    new_ssh_password_credential_id = credential_vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret=new_ssh_password_secret,
    )
    new_ssh_key_passphrase_credential_id = credential_vault.put(
        kind=CredentialKind.SSH_KEY_PASSPHRASE,
        secret=new_ssh_key_passphrase_secret,
    )
    lease_id = get_credential_lease_registry().issue(
        {
            new_password_credential_id,
            new_ssh_password_credential_id,
            new_ssh_key_passphrase_credential_id,
        }
    )

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(
            password_credential_id=new_password_credential_id,
            credential_lease_id=lease_id,
            ssh_enabled=True,
            ssh_host="new-bastion",
            ssh_username="new-tunnel-user",
            ssh_password_credential_id=new_ssh_password_credential_id,
            ssh_pkey_path="C:/keys/new.pem",
            ssh_key_passphrase_credential_id=new_ssh_key_passphrase_credential_id,
        ),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    db_session.refresh(datasource)
    assert datasource.password_credential_id == new_password_credential_id
    assert datasource.ssh_password_credential_id == new_ssh_password_credential_id
    assert datasource.ssh_key_passphrase_credential_id == new_ssh_key_passphrase_credential_id
    assert credential_vault.get(new_password_credential_id) == new_password_secret
    assert credential_vault.get(new_ssh_password_credential_id) == new_ssh_password_secret
    assert credential_vault.get(new_ssh_key_passphrase_credential_id) == new_ssh_key_passphrase_secret
    for credential_id in old_credential_ids:
        assert credential_id is not None
        assert credential_vault.get(credential_id) is None
    serialized_response = str(response.json())
    assert new_password_secret not in serialized_response
    assert new_ssh_password_secret not in serialized_response
    assert new_ssh_key_passphrase_secret not in serialized_response


def test_update_datasource_repairs_missing_credentials_after_runtime_reset(
    client,
    db_session,
    credential_vault,
) -> None:
    datasource = _create_datasource(db_session, credential_vault)
    old_generation = datasource.connection_generation
    datasource.password_credential_id = None
    datasource.status = "needs_credentials"
    db_session.commit()

    new_password_credential_id = credential_vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="re-enrolled-password",
    )
    lease_id = get_credential_lease_registry().issue({new_password_credential_id})

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(
            password_credential_id=new_password_credential_id,
            credential_lease_id=lease_id,
        ),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "active"
    assert body["connection_generation"] == (old_generation or 0) + 1
    db_session.refresh(datasource)
    assert datasource.password_credential_id == new_password_credential_id
    assert datasource.status == "active"


def test_update_datasource_missing_id_returns_404(client) -> None:
    response = client.put(
        "/api/v1/datasources/missing",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DBFOX_ERROR"


def test_update_column_metadata_updates_semantic_fields(client, db_session, credential_vault) -> None:
    datasource = _create_datasource(db_session, credential_vault)
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
