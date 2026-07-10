from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.agent_core.types import AgentRunRequest
import engine.api.datasources.crud as datasource_crud
import engine.datasource as datasource_module
from engine.models import AgentRun, DataSource
from engine.schemas.datasource import DataSourceCreateRequest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def test_agent_request_accepts_only_an_opaque_llm_credential_id() -> None:
    request = AgentRunRequest(
        datasource_id="ds-1",
        question="show orders",
        llm_credential_id="cred_llm_api_key_123",
    )

    assert request.llm_credential_id == "cred_llm_api_key_123"
    assert "api_key" not in request.model_dump()

    with pytest.raises(ValidationError):
        AgentRunRequest(
            datasource_id="ds-1",
            question="show orders",
            api_key="sk-phase1-sentinel",
        )


def test_datasource_requests_reject_plaintext_secret_fields() -> None:
    payload = {
        "name": "warehouse",
        "db_type": "mysql",
        "host": "db.example.test",
        "port": 3306,
        "database_name": "warehouse",
        "username": "readonly",
        "password_credential_id": "cred_datasource_password_123",
        "ssh_password_credential_id": "cred_ssh_password_123",
        "ssh_key_passphrase_credential_id": "cred_ssh_key_passphrase_123",
    }
    request = DataSourceCreateRequest(**payload)

    assert request.password_credential_id == "cred_datasource_password_123"
    assert request.ssh_password_credential_id == "cred_ssh_password_123"
    assert request.ssh_key_passphrase_credential_id == "cred_ssh_key_passphrase_123"

    with pytest.raises(ValidationError):
        DataSourceCreateRequest(**payload, password="db-secret")


def test_datasource_metadata_has_only_credential_reference_columns() -> None:
    columns = set(DataSource.__table__.columns.keys())

    assert {
        "password_credential_id",
        "ssh_password_credential_id",
        "ssh_key_passphrase_credential_id",
    } <= columns
    assert not {
        "password_ciphertext",
        "password_nonce",
        "ssh_password_ciphertext",
        "ssh_password_nonce",
        "ssh_pkey_passphrase_ciphertext",
        "ssh_pkey_passphrase_nonce",
    } & columns


def test_create_datasource_persists_only_opaque_credential_references(db_session, monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    password_credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="db-phase1-sentinel",
    )
    ssh_password_credential_id = vault.put(
        kind=CredentialKind.SSH_PASSWORD,
        secret="ssh-phase1-sentinel",
    )
    ssh_key_passphrase_credential_id = vault.put(
        kind=CredentialKind.SSH_KEY_PASSPHRASE,
        secret="passphrase-phase1-sentinel",
    )
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)

    response = datasource_crud.api_create_datasource(
        DataSourceCreateRequest(
            name="warehouse",
            db_type="sqlite",
            host="",
            port=0,
            database_name="C:/data/warehouse.sqlite",
            username="",
            password_credential_id=password_credential_id,
            ssh_password_credential_id=ssh_password_credential_id,
            ssh_key_passphrase_credential_id=ssh_key_passphrase_credential_id,
        ),
        db_session,
    )

    datasource = db_session.get(DataSource, response["id"])
    assert datasource is not None
    assert datasource.password_credential_id == password_credential_id
    assert datasource.ssh_password_credential_id == ssh_password_credential_id
    assert datasource.ssh_key_passphrase_credential_id == ssh_key_passphrase_credential_id


def test_agent_run_metadata_persists_the_llm_credential_reference_only() -> None:
    columns = set(AgentRun.__table__.columns.keys())

    assert {"llm_credential_id", "api_base", "model_name"} <= columns
    assert "api_key" not in columns


def test_connection_parameters_resolve_a_vault_reference_only_in_memory(monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="db-phase1-connection-sentinel",
    )
    monkeypatch.setattr(datasource_module, "get_credential_vault", lambda: vault)

    params = datasource_module.get_mysql_connection_params({
        "host": "db.example.test",
        "port": 3306,
        "username": "readonly",
        "database_name": "warehouse",
        "password_credential_id": credential_id,
        "ssh_enabled": False,
    })

    assert params["password"] == "db-phase1-connection-sentinel"
    assert "password_ciphertext" not in params
