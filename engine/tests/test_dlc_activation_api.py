"""Tests for the Runtime DLC activation projection API endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engine.dlc import (
    ActivatedDlcIdentity,
    ContributionCompiler,
    DlcPackageService,
    compute_snapshot_id,
)
from engine.dlc.snapshot import (
    RuntimeContributionSnapshot,
)
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.runtime_composition import set_active_runtime_snapshot
from engine.tests.fixtures.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)


def test_dlc_activation_endpoint_baseline_built_ins() -> None:
    """Activation endpoint returns deterministic snapshot_id and empty active_dlcs by default."""
    empty_snapshot = RuntimeContributionSnapshot(
        snapshot_id=compute_snapshot_id(()),
        active_dlcs=(),
        tools=(),
        resource_providers=(),
        resource_resolvers=(),
        context_contributors=(),
        artifact_contracts=(),
        operations=(),
    )
    set_active_runtime_snapshot(empty_snapshot)

    client = TestClient(app)
    headers = {"X-Local-Token": LOCAL_SECURE_TOKEN}

    resp = client.get("/api/v1/dlcs/activation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["snapshot_id"] == empty_snapshot.snapshot_id
    assert data["active_dlcs"] == []


def test_dlc_activation_endpoint_with_active_dlcs(tmp_path: Path) -> None:
    """Activation endpoint reflects active DLCs including frontend entrypoints."""
    priv_key, pub_b64 = generate_test_keypair()
    dlc_service = DlcPackageService(tmp_path / "dlc_root")
    dlc_service.trust_store.add_trusted_key(pub_b64)

    archive_bytes = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.frontend_test",
            "version": "1.2.0",
            "displayName": "Frontend Test Extension",
            "publisher": "acme",
            "extensionApiVersion": "1",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {
                "backend": "backend/entry.py",
                "frontend": "frontend/index.js",
            },
            "permissions": [],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host):\n    pass\n",
            "frontend/index.js": "export function register(host) {}\n",
        },
        private_key=priv_key,
    )

    pkg_path = tmp_path / "test.dbfox-dlc"
    pkg_path.write_bytes(archive_bytes)

    install_result = dlc_service.install_from_file(pkg_path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(install_result.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()
    set_active_runtime_snapshot(snapshot)

    client = TestClient(app)
    headers = {"X-Local-Token": LOCAL_SECURE_TOKEN}

    resp = client.get("/api/v1/dlcs/activation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["snapshot_id"] == snapshot.snapshot_id
    assert len(data["active_dlcs"]) == 1
    active = data["active_dlcs"][0]
    assert active["dlc_id"] == "acme.frontend_test"
    assert active["package_version"] == "1.2.0"
    assert active["package_digest"] == install_result.package_digest
    assert active["frontend_entrypoint"] == "frontend/index.js"


def test_dlc_activation_endpoint_rejects_missing_or_invalid_token() -> None:
    """Activation endpoint enforces local token authentication."""
    client = TestClient(app)

    # Missing token
    resp_no_token = client.get("/api/v1/dlcs/activation")
    assert resp_no_token.status_code == 401

    # Invalid token
    resp_bad_token = client.get("/api/v1/dlcs/activation", headers={"X-Local-Token": "invalid-token"})
    assert resp_bad_token.status_code == 401
