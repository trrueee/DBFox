from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.agent_core.types import AgentRunRequest
import engine.api.credentials as credentials_api
import engine.api.datasources.crud as datasource_crud
from engine.api.credentials import CredentialLeaseRegistry
import engine.datasource as datasource_module
from engine.errors import DataSourceConnectionError
from engine.models import AgentRun, DataSource
from engine.schemas.datasource import (
    DataSourceCreateRequest,
    DataSourceTestRequest,
    DataSourceUpdateRequest,
)
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault
from engine.tools.sandbox.base import ExecutionContext


def _issue_datasource_credential_lease(monkeypatch, *credential_ids: str) -> str:
    leases = CredentialLeaseRegistry()
    monkeypatch.setattr(datasource_crud, "get_credential_lease_registry", lambda: leases)
    return leases.issue(set(credential_ids))


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


def test_tool_execution_context_has_no_serializable_llm_secret_field() -> None:
    assert "api_key" not in ExecutionContext.model_fields

    with pytest.raises(ValidationError):
        ExecutionContext(
            thread_id="thread-1",
            datasource_id="ds-1",
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
    lease_id = _issue_datasource_credential_lease(
        monkeypatch,
        password_credential_id,
        ssh_password_credential_id,
        ssh_key_passphrase_credential_id,
    )

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
            credential_lease_id=lease_id,
        ),
        db_session,
    )

    datasource = db_session.get(DataSource, response["id"])
    assert datasource is not None
    assert datasource.password_credential_id == password_credential_id
    assert datasource.ssh_password_credential_id == ssh_password_credential_id
    assert datasource.ssh_key_passphrase_credential_id == ssh_key_passphrase_credential_id


def test_external_release_cannot_delete_a_credential_after_create_claim(
    db_session,
    monkeypatch,
) -> None:
    vault = InMemoryCredentialVault()
    credentials = CredentialLeaseRegistry()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="claimed-datasource-password",
    )
    lease_id = credentials.issue({credential_id})
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    monkeypatch.setattr(datasource_crud, "get_credential_lease_registry", lambda: credentials)
    monkeypatch.setattr(credentials_api, "get_credential_vault", lambda: vault)
    monkeypatch.setattr(credentials_api, "get_credential_lease_registry", lambda: credentials)

    original_commit = db_session.commit
    release_attempts = 0

    def commit_after_external_release() -> None:
        nonlocal release_attempts
        release_attempts += 1
        credentials_api.api_release_credential_lease(lease_id)
        original_commit()

    monkeypatch.setattr(db_session, "commit", commit_after_external_release)

    response = datasource_crud.api_create_datasource(
        DataSourceCreateRequest(
            name="claimed credential datasource",
            db_type="sqlite",
            host="",
            port=0,
            database_name="C:/data/warehouse.sqlite",
            username="",
            password_credential_id=credential_id,
            credential_lease_id=lease_id,
        ),
        db_session,
    )

    datasource = db_session.get(DataSource, response["id"])
    assert release_attempts >= 1
    assert datasource is not None
    assert datasource.password_credential_id == credential_id
    assert vault.get(credential_id) == "claimed-datasource-password"


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


@pytest.mark.parametrize(
    "connection_builder",
    [
        datasource_module.get_mysql_connection_params,
        datasource_module.get_postgres_connection_params,
    ],
)
def test_network_connection_parameters_fail_closed_without_a_password_credential(
    connection_builder,
) -> None:
    with pytest.raises(DataSourceConnectionError, match="password credential"):
        connection_builder(
            {
                "host": "db.example.test",
                "port": 3306,
                "username": "readonly",
                "database_name": "warehouse",
                "ssh_enabled": False,
            }
        )


def test_datasource_test_never_calls_the_driver_with_an_empty_password(
    monkeypatch,
) -> None:
    driver_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        datasource_crud,
        "test_connection",
        lambda config: driver_calls.append(config),
    )

    with pytest.raises(DataSourceConnectionError, match="password credential"):
        datasource_crud.api_test_connection(
            DataSourceTestRequest(
                db_type="mysql",
                host="db.example.test",
                port=3306,
                database_name="warehouse",
                username="readonly",
            )
        )

    assert driver_calls == []


@pytest.mark.parametrize("exception_factory", [RuntimeError, DataSourceConnectionError])
def test_datasource_test_never_exposes_or_logs_a_driver_exception_sentinel(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
    exception_factory,
) -> None:
    sentinel = "driver-tunnel-sentinel-not-a-redaction-pattern"

    def fail_connection(_config):
        raise exception_factory(sentinel)

    monkeypatch.setattr(datasource_crud, "test_connection", fail_connection)

    with pytest.raises(DataSourceConnectionError) as exc_info:
        datasource_crud.api_test_connection(
            DataSourceTestRequest(
                db_type="sqlite",
                host="",
                port=0,
                database_name="C:/data/warehouse.sqlite",
                username="",
            )
        )

    assert exc_info.value.code == "CONNECTION_FAILED"
    assert str(exc_info.value) == "数据库连接测试失败，请检查连接配置。"
    assert sentinel not in repr(exc_info.value)
    assert sentinel not in caplog.text


def test_datasource_test_never_logs_a_temporary_tunnel_stop_sentinel(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "driver-tunnel-sentinel-not-a-redaction-pattern"
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="temporary-tunnel-password",
    )
    lease_id = _issue_datasource_credential_lease(monkeypatch, credential_id)
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)

    class FailingStopTunnel:
        local_bind_port = 13306

        def stop(self) -> None:
            raise RuntimeError(sentinel)

    monkeypatch.setattr(
        datasource_module,
        "open_temporary_tunnel",
        lambda _config: FailingStopTunnel(),
    )
    monkeypatch.setattr(
        datasource_module.pymysql,
        "connect",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("connection failure")),
    )

    with pytest.raises(DataSourceConnectionError) as exc_info:
        datasource_crud.api_test_connection(
            DataSourceTestRequest(
                db_type="mysql",
                host="db.example.test",
                port=3306,
                database_name="warehouse",
                username="reader",
                password_credential_id=credential_id,
                ssh_enabled=True,
                ssh_host="jump.example.test",
                ssh_port=22,
                ssh_username="jump-user",
                credential_lease_id=lease_id,
            )
        )

    assert str(exc_info.value) == "数据库连接测试失败，请检查连接配置。"
    assert sentinel not in repr(exc_info.value)
    assert sentinel not in caplog.text


def test_datasource_test_rejects_a_client_claimed_lease_without_deleting_a_saved_credential(
    monkeypatch,
) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="saved-datasource-password",
    )
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    driver_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        datasource_crud,
        "test_connection",
        lambda config: driver_calls.append(config),
    )

    with pytest.raises(Exception):
        datasource_crud.api_test_connection(
            DataSourceTestRequest(
                db_type="mysql",
                host="db.example.test",
                port=3306,
                database_name="warehouse",
                username="readonly",
                password_credential_id=credential_id,
                credential_lease_id="lease_attacker_controlled",
            )
        )

    assert vault.get(credential_id) == "saved-datasource-password"
    assert driver_calls == []


@pytest.mark.parametrize("connection_fails", [False, True])
def test_datasource_test_cleans_up_transient_credentials(
    monkeypatch,
    connection_fails: bool,
) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="transient-datasource-password",
    )
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    lease_id = _issue_datasource_credential_lease(monkeypatch, credential_id)

    def fake_test_connection(_config):
        if connection_fails:
            raise RuntimeError("connection-sentinel")
        return {"ok": True}

    monkeypatch.setattr(datasource_crud, "test_connection", fake_test_connection)
    request = DataSourceTestRequest(
        db_type="mysql",
        host="db.example.test",
        port=3306,
        database_name="warehouse",
        username="readonly",
        password_credential_id=credential_id,
        credential_lease_id=lease_id,
    )

    if connection_fails:
        with pytest.raises(Exception):
            datasource_crud.api_test_connection(request)
    else:
        assert datasource_crud.api_test_connection(request) == {"ok": True}

    assert vault.get(credential_id) is None


def test_failed_datasource_create_cleans_up_transient_credentials(db_session, monkeypatch) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="transient-create-password",
    )
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    lease_id = _issue_datasource_credential_lease(monkeypatch, credential_id)
    request = DataSourceCreateRequest(
        name="warehouse",
        db_type="mysql",
        host="db.example.test",
        port=3306,
        database_name="warehouse",
        username="readonly",
        password_credential_id=credential_id,
        ssl_enabled=True,
        ssl_verify_identity=True,
        credential_lease_id=lease_id,
    )

    with pytest.raises(Exception):
        datasource_crud.api_create_datasource(request, db_session)

    assert vault.get(credential_id) is None


def test_successful_datasource_update_commits_the_server_issued_credential_lease(
    db_session,
    monkeypatch,
) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="updated-datasource-password",
    )
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    lease_id = _issue_datasource_credential_lease(monkeypatch, credential_id)
    datasource = DataSource(
        id="ds-update-lease-success",
        name="before update",
        db_type="sqlite",
        host="",
        port=0,
        database_name="C:/data/warehouse.sqlite",
        username="",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()

    datasource_crud.api_update_datasource(
        datasource.id,
        DataSourceUpdateRequest(
            name="after update",
            db_type="sqlite",
            host="",
            port=0,
            database_name="C:/data/warehouse.sqlite",
            username="",
            password_credential_id=credential_id,
            credential_lease_id=lease_id,
        ),
        db_session,
    )

    assert db_session.get(DataSource, datasource.id).password_credential_id == credential_id
    assert vault.get(credential_id) == "updated-datasource-password"


def test_failed_datasource_update_releases_the_server_issued_credential_lease(
    db_session,
    monkeypatch,
) -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="failed-update-password",
    )
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    lease_id = _issue_datasource_credential_lease(monkeypatch, credential_id)
    datasource = DataSource(
        id="ds-update-lease-failure",
        name="before update",
        db_type="sqlite",
        host="",
        port=0,
        database_name="C:/data/warehouse.sqlite",
        username="",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()

    with pytest.raises(DataSourceConnectionError):
        datasource_crud.api_update_datasource(
            datasource.id,
            DataSourceUpdateRequest(
                name="after update",
                db_type="mysql",
                host="db.example.test",
                port=3306,
                database_name="warehouse",
                username="readonly",
                password_credential_id=credential_id,
                credential_lease_id=lease_id,
                ssl_enabled=True,
                ssl_verify_identity=True,
            ),
            db_session,
        )

    assert vault.get(credential_id) is None
