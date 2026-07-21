from __future__ import annotations

from typing import Any

import pytest

from engine.api.credentials import get_credential_lease_registry
from engine.api.datasources import crud as datasource_crud
from engine.connectivity._pools import _get_mysql_pool
from engine.connectivity.lifecycle import DatasourceResourceLifecycle
from engine.connectivity.profile import ConnectionProfile
from engine.errors import DataSourceConnectionError
from engine.models import DEFAULT_PROJECT_ID, DataSource, Project
from engine.schemas.datasource import DataSourceUpdateRequest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault
from engine.sql.pool_registry import get_pool_registry
from engine.tunnel import TunnelManager


def _profile(
    *,
    generation: int,
    host: str = "db-a.internal.test",
    password_credential_id: str = "cred_datasource_password_a",
    ssh_host: str = "jump-a.internal.test",
    ssh_password_credential_id: str = "cred_ssh_password_a",
) -> ConnectionProfile:
    return ConnectionProfile.from_mapping(
        {
            "id": "datasource-lifecycle",
            "is_managed": True,
            "connection_generation": generation,
            "db_type": "mysql",
            "host": host,
            "port": 3306,
            "database_name": "warehouse",
            "username": "readonly",
            "password_credential_id": password_credential_id,
            "ssh_enabled": True,
            "ssh_host": ssh_host,
            "ssh_port": 22,
            "ssh_username": "jump-user",
            "ssh_password_credential_id": ssh_password_credential_id,
        }
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"host": "db-b.internal.test"},
        {"ssh_host": "jump-b.internal.test"},
        {"password_credential_id": "cred_datasource_password_b"},
    ],
    ids=["host", "ssh", "password"],
)
def test_committed_resource_replacement_fences_each_rotated_profile(
    changed: dict[str, str],
) -> None:
    events: list[str] = []
    previous = _profile(generation=1)
    current = _profile(generation=2, **changed)
    lifecycle = DatasourceResourceLifecycle(
        pool_disposer=lambda datasource_id: events.append(f"pool:{datasource_id}") or 1,
        tunnel_closer=lambda datasource_id: events.append(f"tunnel:{datasource_id}"),
    )

    assert lifecycle.replace(previous, current) is True
    assert events == ["pool:datasource-lifecycle", "tunnel:datasource-lifecycle"]
    assert previous.managed_resource_key != current.managed_resource_key

    with pytest.raises(DataSourceConnectionError, match="replaced"):
        with lifecycle.checkout(previous):
            pytest.fail("a prior generation must never acquire a new connection")

    with lifecycle.checkout(current):
        pass


def test_generation_prevents_reverted_profile_from_reusing_old_resources() -> None:
    events: list[str] = []
    initial = _profile(generation=1)
    changed = _profile(generation=2, host="db-b.internal.test")
    restored = _profile(generation=3)
    lifecycle = DatasourceResourceLifecycle(
        pool_disposer=lambda datasource_id: events.append(f"pool:{datasource_id}") or 1,
        tunnel_closer=lambda datasource_id: events.append(f"tunnel:{datasource_id}"),
    )

    assert initial.profile_fingerprint == restored.profile_fingerprint
    assert initial.managed_resource_key != restored.managed_resource_key
    assert lifecycle.replace(initial, changed) is True
    assert lifecycle.replace(changed, restored) is True

    with pytest.raises(DataSourceConnectionError, match="replaced"):
        with lifecycle.checkout(initial):
            pytest.fail("a reverted profile must not reuse generation-one resources")
    with lifecycle.checkout(restored):
        pass

    assert events == [
        "pool:datasource-lifecycle",
        "tunnel:datasource-lifecycle",
        "pool:datasource-lifecycle",
        "tunnel:datasource-lifecycle",
    ]


def test_managed_tunnel_uses_generation_and_profile_fingerprint_keys(monkeypatch) -> None:
    manager = TunnelManager()

    class FakeTunnel:
        def __init__(self, port: int) -> None:
            self.local_bind_port = port
            self.is_active = True
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True
            self.is_active = False

    created = [FakeTunnel(21001), FakeTunnel(21002)]
    monkeypatch.setattr(manager, "_start_physical_tunnel", lambda _config: created.pop(0))
    previous = _profile(generation=1)
    current = _profile(generation=2, ssh_host="jump-b.internal.test")

    first = manager.get_or_reconnect(previous.tunnel_config())
    second = manager.get_or_reconnect(current.tunnel_config())

    assert first is not second
    assert len(manager._tunnels) == 2
    manager.close_tunnel("datasource-lifecycle")
    assert first.stopped is True
    assert second.stopped is True
    assert manager._tunnels == {}


def test_pool_creator_does_not_retain_or_use_a_deleted_password(monkeypatch) -> None:
    import engine.connectivity._pools as pool_module

    vault = InMemoryCredentialVault()
    credential_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="database-password-that-must-not-live-in-a-pool-closure",
    )
    profile = _profile(generation=1, password_credential_id=credential_id)
    driver_calls: list[dict[str, Any]] = []
    get_pool_registry().dispose_datasource("datasource-lifecycle")
    monkeypatch.setattr(
        pool_module.pymysql,
        "connect",
        lambda **params: driver_calls.append(params),
    )

    pool = _get_mysql_pool(
        profile,
        host="127.0.0.1",
        port=3306,
        params={"user": "readonly", "database": "warehouse"},
        vault=vault,
    )
    vault.delete(credential_id)

    with pytest.raises(DataSourceConnectionError, match="Credential reference"):
        pool.connect()

    assert driver_calls == []
    get_pool_registry().dispose_datasource("datasource-lifecycle")


class _RecordingVault(InMemoryCredentialVault):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    def delete(self, credential_id: str) -> None:
        self._events.append(f"delete:{credential_id}")
        super().delete(credential_id)


class _RecordingLifecycle:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.replacements: list[tuple[ConnectionProfile, ConnectionProfile]] = []
        self.retirements: list[str] = []

    def replace(self, previous: ConnectionProfile, current: ConnectionProfile) -> bool:
        self.events.append("resources-invalidated")
        self.replacements.append((previous, current))
        return True

    def recover(self, current: ConnectionProfile) -> bool:
        self.events.append("resources-recovered")
        return True

    def retire(self, datasource_id: str) -> None:
        self.events.append("resources-retired")
        self.retirements.append(datasource_id)


def _seed_datasource(db_session, vault: InMemoryCredentialVault) -> DataSource:
    if db_session.get(Project, DEFAULT_PROJECT_ID) is None:
        db_session.add(
            Project(
                id=DEFAULT_PROJECT_ID,
                name="Datasource lifecycle test project",
                description="Project required by the datasource foreign key.",
            )
        )
        db_session.flush()
    datasource = DataSource(
        id="datasource-lifecycle-api",
        project_id=DEFAULT_PROJECT_ID,
        name="Lifecycle source",
        db_type="mysql",
        host="db-a.internal.test",
        port=3306,
        database_name="warehouse",
        username="readonly",
        password_credential_id=vault.put(
            kind=CredentialKind.DATASOURCE_PASSWORD,
            secret="old-database-password",
        ),
        ssh_enabled=True,
        ssh_host="jump-a.internal.test",
        ssh_port=22,
        ssh_username="jump-user",
        ssh_password_credential_id=vault.put(
            kind=CredentialKind.SSH_PASSWORD,
            secret="old-ssh-password",
        ),
        ssh_pkey_path=None,
        connection_generation=1,
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()
    return datasource


def _update_request(**overrides: Any) -> DataSourceUpdateRequest:
    values: dict[str, Any] = {
        "name": "Lifecycle source",
        "db_type": "mysql",
        "host": "db-b.internal.test",
        "port": 3306,
        "database_name": "warehouse",
        "username": "readonly",
        "connection_mode": "direct",
        "is_read_only": True,
        "env": "prod",
        "ssh_enabled": True,
        "ssh_host": "jump-b.internal.test",
        "ssh_port": 22,
        "ssh_username": "jump-user",
        "ssh_pkey_path": None,
        "ssl_enabled": False,
        "ssl_verify_identity": True,
    }
    values.update(overrides)
    return DataSourceUpdateRequest(**values)


def test_update_invalidates_resources_before_deleting_replaced_credentials(
    db_session,
    monkeypatch,
) -> None:
    events: list[str] = []
    vault = _RecordingVault(events)
    datasource = _seed_datasource(db_session, vault)
    old_password_id = datasource.password_credential_id
    assert old_password_id is not None
    new_password_id = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="new-database-password",
    )
    lease_id = get_credential_lease_registry().issue({new_password_id})
    lifecycle = _RecordingLifecycle(events)
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    monkeypatch.setattr(datasource_crud, "get_datasource_resource_lifecycle", lambda: lifecycle)

    response = datasource_crud.api_update_datasource(
        datasource.id,
        _update_request(
            password_credential_id=new_password_id,
            credential_lease_id=lease_id,
        ),
        db_session,
    )

    db_session.refresh(datasource)
    assert response["connection_generation"] == 2
    assert datasource.connection_generation == 2
    assert datasource.password_credential_id == new_password_id
    assert lifecycle.replacements
    previous, current = lifecycle.replacements[0]
    assert previous.connection_generation == 1
    assert current.connection_generation == 2
    assert events.index("resources-invalidated") < events.index(f"delete:{old_password_id}")
    assert vault.get(old_password_id) is None


def test_failed_update_never_invalidates_resources_or_deletes_old_credentials(
    db_session,
    monkeypatch,
) -> None:
    events: list[str] = []
    vault = _RecordingVault(events)
    datasource = _seed_datasource(db_session, vault)
    old_password_id = datasource.password_credential_id
    assert old_password_id is not None
    lifecycle = _RecordingLifecycle(events)
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    monkeypatch.setattr(datasource_crud, "get_datasource_resource_lifecycle", lambda: lifecycle)
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))

    with pytest.raises(RuntimeError, match="commit failed"):
        datasource_crud.api_update_datasource(
            datasource.id,
            _update_request(),
            db_session,
        )

    assert lifecycle.replacements == []
    assert f"delete:{old_password_id}" not in events
    assert vault.get(old_password_id) == "old-database-password"


def test_delete_retires_resources_before_deleting_credentials(
    db_session,
    monkeypatch,
) -> None:
    events: list[str] = []
    vault = _RecordingVault(events)
    datasource = _seed_datasource(db_session, vault)
    old_password_id = datasource.password_credential_id
    assert old_password_id is not None
    lifecycle = _RecordingLifecycle(events)
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    monkeypatch.setattr(datasource_crud, "get_datasource_resource_lifecycle", lambda: lifecycle)
    monkeypatch.setattr("engine.policy.confirmation_bypass_enabled", lambda: True)

    response = datasource_crud.api_delete_datasource(datasource.id, db=db_session)

    assert response["success"] is True
    assert lifecycle.retirements == [datasource.id]
    assert events.index("resources-retired") < events.index(f"delete:{old_password_id}")
    assert db_session.get(DataSource, datasource.id) is None
    assert vault.get(old_password_id) is None


def test_failed_delete_never_retires_resources_or_deletes_credentials(
    db_session,
    monkeypatch,
) -> None:
    events: list[str] = []
    vault = _RecordingVault(events)
    datasource = _seed_datasource(db_session, vault)
    old_password_id = datasource.password_credential_id
    assert old_password_id is not None
    lifecycle = _RecordingLifecycle(events)
    monkeypatch.setattr(datasource_crud, "get_credential_vault", lambda: vault)
    monkeypatch.setattr(datasource_crud, "get_datasource_resource_lifecycle", lambda: lifecycle)
    monkeypatch.setattr("engine.policy.confirmation_bypass_enabled", lambda: True)
    monkeypatch.setattr(
        db_session,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        datasource_crud.api_delete_datasource(datasource.id, db=db_session)

    assert lifecycle.retirements == []
    assert f"delete:{old_password_id}" not in events
    assert vault.get(old_password_id) == "old-database-password"
