"""R4.1 DLC lifecycle API desired-state and active-runtime contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from engine.api.dlc_lifecycle import (
    get_dlc_lifecycle_service,
    get_dlc_runtime_snapshot,
)
from engine.dlc import DlcPackageService, compute_snapshot_id
from engine.dlc.snapshot import (
    ActivatedDlcIdentity,
    DlcActivationFailure,
    RuntimeContributionSnapshot,
)
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.tests.fixtures.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)


def _snapshot(
    *active_dlcs: ActivatedDlcIdentity,
    failures: tuple[DlcActivationFailure, ...] = (),
) -> RuntimeContributionSnapshot:
    active = tuple(active_dlcs)
    return RuntimeContributionSnapshot(
        snapshot_id=compute_snapshot_id(active),
        active_dlcs=active,
        tools=(),
        resource_providers=(),
        resource_resolvers=(),
        context_contributors=(),
        artifact_contracts=(),
        operations=(),
        activation_failures=failures,
    )


def _write_v2_package(path: Path) -> tuple[str, str]:
    private_key, public_key_base64 = generate_test_keypair()
    path.write_bytes(
        build_test_dlc_archive(
            manifest_data={
                "manifestSchemaVersion": 2,
                "id": "acme.echo",
                "version": "1.0.0",
                "displayName": "Acme Echo",
                "publisher": "acme",
                "publisherKey": public_key_base64,
                "description": "Lifecycle API fixture",
                "extensionApiVersion": "1",
                "requiresDbfox": ">=1.0.0",
                "entrypoints": {
                    "backend": "backend/entry.py",
                    "frontend": "frontend/index.js",
                },
                "permissions": ["network:api.example.com"],
            },
            payload_files={
                "backend/__init__.py": "",
                "backend/entry.py": "def register(host):\n    pass\n",
                "frontend/index.js": "export function register(host) {}\n",
            },
            private_key=private_key,
        )
    )
    service = DlcPackageService(path.parent / "inspection-runtime")
    inspection = service.inspect_from_file(path)
    assert inspection.publisher_key_id is not None
    return inspection.package_digest, inspection.publisher_key_id


def _client_for(
    service: DlcPackageService,
    snapshot_holder: dict[str, RuntimeContributionSnapshot],
) -> TestClient:
    app.dependency_overrides[get_dlc_lifecycle_service] = lambda: service
    app.dependency_overrides[get_dlc_runtime_snapshot] = lambda: snapshot_holder["value"]
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


def _problem(response: Any, code: str, status_code: int) -> None:
    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == code
    assert body["status"] == status_code
    assert body["request_id"]


def test_lifecycle_api_install_enable_disable_restart_and_uninstall(tmp_path: Path) -> None:
    archive_path = (tmp_path / "acme.echo.dbfox-dlc").resolve()
    expected_digest, expected_fingerprint = _write_v2_package(archive_path)
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    snapshot_holder = {"value": _snapshot()}
    client = _client_for(service, snapshot_holder)
    try:
        inspect_response = client.post(
            "/api/v1/dlcs/packages/inspect",
            headers=_headers(),
            json={"archive_path": str(archive_path)},
        )
        assert inspect_response.status_code == 200
        inspection = inspect_response.json()
        assert inspection == {
            "dlc_id": "acme.echo",
            "version": "1.0.0",
            "display_name": "Acme Echo",
            "description": "Lifecycle API fixture",
            "publisher": "acme",
            "publisher_fingerprint": expected_fingerprint,
            "package_digest": expected_digest,
            "trust_status": "untrusted",
            "trust_required": True,
            "permissions": ["network:api.example.com"],
            "backend_entrypoint_present": True,
            "frontend_entrypoint_present": True,
        }

        install_before_trust = client.post(
            "/api/v1/dlcs/install",
            headers=_headers(),
            json={"archive_path": str(archive_path)},
        )
        _problem(install_before_trust, "TRUST_REQUIRED", 409)

        forged_trust = client.post(
            "/api/v1/dlcs/publishers/trust",
            headers=_headers(),
            json={
                "archive_path": str(archive_path),
                "package_digest": "0" * 64,
                "publisher_fingerprint": expected_fingerprint,
            },
        )
        _problem(forged_trust, "PACKAGE_TAMPERED", 400)
        assert not service.trust_store.is_trusted(expected_fingerprint)

        trust_response = client.post(
            "/api/v1/dlcs/publishers/trust",
            headers=_headers(),
            json={
                "archive_path": str(archive_path),
                "package_digest": expected_digest,
                "publisher_fingerprint": expected_fingerprint,
            },
        )
        assert trust_response.status_code == 200
        assert trust_response.json() == {
            "publisher_fingerprint": expected_fingerprint,
            "trusted": True,
        }

        install_response = client.post(
            "/api/v1/dlcs/install",
            headers=_headers(),
            json={"archive_path": str(archive_path)},
        )
        assert install_response.status_code == 201
        installed = install_response.json()
        assert installed["state"] == "installed_disabled"
        assert installed["desired_enabled"] is False
        assert installed["active"] is False
        assert installed["restart_state"] == "none"

        duplicate_response = client.post(
            "/api/v1/dlcs/install",
            headers=_headers(),
            json={"archive_path": str(archive_path)},
        )
        assert duplicate_response.status_code == 201
        assert duplicate_response.json()["selected_digest"] == expected_digest
        assert duplicate_response.json()["state"] == "installed_disabled"

        conflicting_path = (tmp_path / "acme.echo-conflict.dbfox-dlc").resolve()
        conflicting_digest, conflicting_fingerprint = _write_v2_package(conflicting_path)
        assert conflicting_digest != expected_digest
        conflict_trust = client.post(
            "/api/v1/dlcs/publishers/trust",
            headers=_headers(),
            json={
                "archive_path": str(conflicting_path),
                "package_digest": conflicting_digest,
                "publisher_fingerprint": conflicting_fingerprint,
            },
        )
        assert conflict_trust.status_code == 200
        conflicting_install = client.post(
            "/api/v1/dlcs/install",
            headers=_headers(),
            json={"archive_path": str(conflicting_path)},
        )
        _problem(conflicting_install, "CONFLICTING_DIGEST", 409)

        list_response = client.get("/api/v1/dlcs", headers=_headers())
        assert list_response.status_code == 200
        assert list_response.json()["snapshot_id"] == snapshot_holder["value"].snapshot_id
        assert [item["dlc_id"] for item in list_response.json()["dlcs"]] == ["acme.echo"]

        enable_response = client.post(
            "/api/v1/dlcs/acme.echo/enable",
            headers=_headers(),
        )
        assert enable_response.status_code == 200
        assert enable_response.json()["state"] == "enable_pending_restart"
        assert enable_response.json()["desired_enabled"] is True
        assert enable_response.json()["active"] is False
        assert enable_response.json()["restart_state"] == "required"

        snapshot_holder["value"] = _snapshot(
            ActivatedDlcIdentity(
                dlc_id="acme.echo",
                package_version="1.0.0",
                package_digest=expected_digest,
                publisher_key_id=expected_fingerprint,
                frontend_entrypoint="frontend/index.js",
            )
        )
        active_response = client.get("/api/v1/dlcs/acme.echo", headers=_headers())
        assert active_response.status_code == 200
        assert active_response.json()["state"] == "active"
        assert active_response.json()["active_digest"] == expected_digest
        assert active_response.json()["restart_state"] == "none"

        uninstall_while_desired = client.delete(
            "/api/v1/dlcs/acme.echo",
            headers=_headers(),
        )
        _problem(uninstall_while_desired, "DLC_DISABLE_REQUIRED", 409)

        disable_response = client.post(
            "/api/v1/dlcs/acme.echo/disable",
            headers=_headers(),
        )
        assert disable_response.status_code == 200
        assert disable_response.json()["state"] == "disable_pending_restart"
        assert disable_response.json()["desired_enabled"] is False
        assert disable_response.json()["active"] is True

        uninstall_while_active = client.delete(
            "/api/v1/dlcs/acme.echo",
            headers=_headers(),
        )
        _problem(uninstall_while_active, "DLC_ACTIVE", 409)

        data_file = service.storage_root / "data" / "acme.echo" / "state.sqlite3"
        data_file.parent.mkdir(parents=True)
        data_file.write_text("retained", encoding="utf-8")
        snapshot_holder["value"] = _snapshot()

        uninstall_response = client.delete(
            "/api/v1/dlcs/acme.echo",
            headers=_headers(),
        )
        assert uninstall_response.status_code == 200
        assert uninstall_response.json() == {
            "dlc_id": "acme.echo",
            "package_digest": expected_digest,
            "executable_bytes_removed": True,
            "data_retained": True,
        }
        assert not service.store.get_package_dir(expected_digest).exists()
        assert data_file.read_text(encoding="utf-8") == "retained"

        missing_response = client.get("/api/v1/dlcs/acme.echo", headers=_headers())
        _problem(missing_response, "DLC_NOT_INSTALLED", 404)
    finally:
        app.dependency_overrides.clear()


def test_lifecycle_projection_reports_activation_failure(tmp_path: Path) -> None:
    archive_path = (tmp_path / "acme.echo.dbfox-dlc").resolve()
    digest, fingerprint = _write_v2_package(archive_path)
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    service.trust_publisher_from_file(
        archive_path,
        expected_package_digest=digest,
        expected_publisher_key_id=fingerprint,
    )
    service.install_from_file(archive_path)
    service.set_desired_enabled("acme.echo", True)
    snapshot_holder = {
        "value": _snapshot(
            failures=(
                DlcActivationFailure(
                    dlc_id="acme.echo",
                    error_code="backend_import_failed",
                    message="Backend registration failed safely.",
                ),
            )
        )
    }
    client = _client_for(service, snapshot_holder)
    try:
        response = client.get("/api/v1/dlcs/acme.echo", headers=_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "activation_failed"
        assert body["restart_state"] == "failed"
        assert body["active"] is False
        assert body["activation_failure"] == {
            "code": "BACKEND_IMPORT_FAILED",
            "message": "Backend registration failed safely.",
        }
    finally:
        app.dependency_overrides.clear()


def test_lifecycle_api_rejects_unauthenticated_and_non_package_paths(tmp_path: Path) -> None:
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")
    snapshot_holder = {"value": _snapshot()}
    client = _client_for(service, snapshot_holder)
    try:
        missing_token = client.get("/api/v1/dlcs")
        _problem(missing_token, "UNAUTHORIZED_ENGINE_ACCESS", 401)

        invalid_path = client.post(
            "/api/v1/dlcs/packages/inspect",
            headers=_headers(),
            json={"archive_path": str((tmp_path / "not-a-package.zip").resolve())},
        )
        _problem(invalid_path, "VALIDATION_ERROR", 422)

        for action in ("enable", "disable"):
            missing_transition = client.post(
                f"/api/v1/dlcs/acme.missing/{action}",
                headers=_headers(),
            )
            _problem(missing_transition, "DLC_NOT_INSTALLED", 404)

        missing_uninstall = client.delete(
            "/api/v1/dlcs/acme.missing",
            headers=_headers(),
        )
        _problem(missing_uninstall, "DLC_NOT_INSTALLED", 404)
    finally:
        app.dependency_overrides.clear()
