from __future__ import annotations

from pathlib import Path

import pytest

from engine.dlc.api import DlcRuntimeInfo
from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.host import DefaultBackendExtensionHost, StagedDlcContributions
from engine.dlc.manifest import DlcManifest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def _host(tmp_path: Path, *, permissions: list[str]) -> DefaultBackendExtensionHost:
    manifest = DlcManifest.model_validate(
        {
            "manifestSchemaVersion": 1,
            "id": "acme.database",
            "version": "1.0.0",
            "displayName": "Database",
            "publisher": "acme",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": permissions,
        }
    )
    staging = StagedDlcContributions(
        dlc_id=manifest.id,
        package_digest="a" * 64,
        manifest=manifest,
        runtime_info=DlcRuntimeInfo(
            dlc_id=manifest.id,
            package_version=manifest.version,
            package_digest="a" * 64,
            data_path=tmp_path,
        ),
    )
    return DefaultBackendExtensionHost(staging)


def test_credential_broker_resolves_only_declared_exact_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = InMemoryCredentialVault()
    password_ref = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="secret-value",
    )
    ssh_ref = vault.put(kind=CredentialKind.SSH_PASSWORD, secret="ssh-secret")
    monkeypatch.setattr("engine.dlc.host.get_credential_vault", lambda: vault)
    host = _host(tmp_path, permissions=["credentials:datasource_password"])

    assert host.credentials.get(
        password_ref,
        kind="datasource_password",
    ) == "secret-value"
    assert host.credentials.get(
        ssh_ref,
        kind="datasource_password",
    ) is None
    assert not hasattr(host.credentials, "keys")
    assert not hasattr(host.credentials, "vault")


def test_credential_broker_rejects_undeclared_or_unknown_kinds(tmp_path: Path) -> None:
    host = _host(tmp_path, permissions=[])
    with pytest.raises(DlcError) as undeclared:
        host.credentials.get(
            "cred_datasource_password_example",
            kind="datasource_password",
        )
    assert undeclared.value.code is DlcErrorCode.PERMISSION_VIOLATION

    with pytest.raises(DlcError) as unknown:
        host.credentials.get("cred_unknown_example", kind="unknown")
    assert unknown.value.code is DlcErrorCode.PERMISSION_VIOLATION


def test_credential_probe_registration_requires_manifest_permission(
    tmp_path: Path,
) -> None:
    host = _host(tmp_path, permissions=[])

    with pytest.raises(DlcError) as denied:
        host.credentials.register_reference_probe(lambda _refs: False)

    assert denied.value.code is DlcErrorCode.PERMISSION_VIOLATION


def test_credential_probe_registration_is_unique_per_capability(
    tmp_path: Path,
) -> None:
    host = _host(tmp_path, permissions=["credentials:datasource_password"])
    host.credentials.register_reference_probe(lambda _refs: False)

    with pytest.raises(DlcError) as duplicate:
        host.credentials.register_reference_probe(lambda _refs: True)

    assert duplicate.value.code is DlcErrorCode.REGISTRATION_CONFLICT
