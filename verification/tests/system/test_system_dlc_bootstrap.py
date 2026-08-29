from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from engine.dlc.package_builder import (
    build_dlc_package,
    build_dlc_package_from_source,
    collect_payload_files,
    read_manifest_template,
)
from engine.dlc.registry import InstalledDlcRegistry
from engine.dlc.system_bundle import (
    SystemDlcBundleManifest,
    SystemDlcPackagePin,
    bootstrap_system_dlcs,
)
from engine.dlc.trust import DlcTrustStore, public_key_to_base64
from engine.runtime_composition import initialize_runtime_snapshot, set_active_runtime_snapshot
from scripts.build_system_dlc_bundle import (
    _development_version,
    build_system_dlc_bundle,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_DLC_SOURCE = REPOSITORY_ROOT / "dlcs" / "dbfox.workspace"


@pytest.fixture(autouse=True)
def _restore_artifact_contract_registry():
    from engine.agent.artifact import artifact_payload_contracts

    original_contracts = dict(artifact_payload_contracts._contracts)
    original_frozen = artifact_payload_contracts._frozen
    artifact_payload_contracts._frozen = False
    artifact_payload_contracts._contracts = {
        key: validator
        for key, validator in artifact_payload_contracts._contracts.items()
        if not key[0].startswith("dbfox.workspace.")
    }
    yield
    artifact_payload_contracts._contracts = original_contracts
    artifact_payload_contracts._frozen = original_frozen


def _workspace_bundle(tmp_path: Path) -> tuple[Path, Path]:
    private_key = ed25519.Ed25519PrivateKey.generate()
    built = build_dlc_package_from_source(
        WORKSPACE_DLC_SOURCE,
        private_key=private_key,
    )
    package_root = tmp_path / "system-dlcs"
    package_root.mkdir()
    filename = "dbfox.workspace.dbfox-dlc"
    (package_root / filename).write_bytes(built.archive_bytes)
    manifest = SystemDlcBundleManifest(
        publisher_public_key=public_key_to_base64(private_key.public_key()),
        packages=(
            SystemDlcPackagePin(
                dlc_id=built.manifest.id,
                version=built.manifest.version,
                filename=filename,
                package_digest=built.package_digest,
            ),
        ),
    )
    manifest_path = tmp_path / "embedded-system-dlcs.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json")),
        encoding="utf-8",
    )
    return package_root, manifest_path


def _versioned_workspace_bundle(
    tmp_path: Path,
    private_key: ed25519.Ed25519PrivateKey,
    version: str,
    *,
    development: bool,
) -> tuple[Path, Path, str]:
    manifest_data = read_manifest_template(WORKSPACE_DLC_SOURCE)
    manifest_data["version"] = version
    built = build_dlc_package(
        manifest_data,
        collect_payload_files(WORKSPACE_DLC_SOURCE),
        private_key=private_key,
    )
    package_root = tmp_path / "system-dlcs"
    package_root.mkdir(parents=True)
    filename = "dbfox.workspace.dbfox-dlc"
    (package_root / filename).write_bytes(built.archive_bytes)
    manifest = SystemDlcBundleManifest(
        development=development,
        publisher_public_key=public_key_to_base64(private_key.public_key()),
        packages=(
            SystemDlcPackagePin(
                dlc_id=built.manifest.id,
                version=built.manifest.version,
                filename=filename,
                package_digest=built.package_digest,
            ),
        ),
    )
    manifest_path = tmp_path / "embedded-system-dlcs.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json")),
        encoding="utf-8",
    )
    return package_root, manifest_path, built.package_digest


def test_bootstrap_installs_enables_and_preserves_explicit_disable(tmp_path: Path) -> None:
    package_root, manifest_path = _workspace_bundle(tmp_path)
    storage_root = tmp_path / "installed"

    result = bootstrap_system_dlcs(
        storage_root,
        package_root,
        manifest_path=manifest_path,
    )
    registry = InstalledDlcRegistry(storage_root)
    installed = registry.get_installed_dlc("dbfox.workspace")

    assert result.dlc_ids == ("dbfox.workspace",)
    assert installed is not None
    assert installed.desired_enabled is True

    registry.set_desired_enabled("dbfox.workspace", False)
    bootstrap_system_dlcs(
        storage_root,
        package_root,
        manifest_path=manifest_path,
    )

    preserved = registry.get_installed_dlc("dbfox.workspace")
    assert preserved is not None
    assert preserved.desired_enabled is False


def test_development_bootstrap_rotates_package_bytes_and_preserves_owned_data(
    tmp_path: Path,
) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    first_root, first_manifest, first_digest = _versioned_workspace_bundle(
        tmp_path / "first",
        private_key,
        "2.1.0-dev.000000000001",
        development=True,
    )
    storage_root = tmp_path / "installed"
    bootstrap_system_dlcs(storage_root, first_root, manifest_path=first_manifest)
    registry = InstalledDlcRegistry(storage_root)
    registry.set_desired_enabled("dbfox.workspace", False)
    owned_data = storage_root / "data" / "dbfox.workspace" / "sentinel.txt"
    owned_data.parent.mkdir(parents=True)
    owned_data.write_text("preserved", encoding="utf-8")

    second_root, second_manifest, second_digest = _versioned_workspace_bundle(
        tmp_path / "second",
        private_key,
        "2.1.0-dev.000000000002",
        development=True,
    )
    bootstrap_system_dlcs(storage_root, second_root, manifest_path=second_manifest)

    installed = registry.get_installed_dlc("dbfox.workspace")
    assert installed is not None
    assert installed.selected_digest == second_digest
    assert installed.desired_enabled is False
    assert [item.package_digest for item in installed.installed_versions] == [
        second_digest
    ]
    assert first_digest != second_digest
    assert owned_data.read_text(encoding="utf-8") == "preserved"


def test_development_version_is_reproducible_and_content_addressed() -> None:
    manifest = {"version": "2.1.0", "id": "dbfox.probe"}
    first = _development_version(manifest, {"backend/entry.py": b"one"})
    repeated = _development_version(manifest, {"backend/entry.py": b"one"})
    changed = _development_version(manifest, {"backend/entry.py": b"two"})

    assert first == repeated
    assert first.startswith("2.1.0-dev.")
    assert changed != first


def test_bootstrap_rejects_package_bytes_outside_the_embedded_digest(tmp_path: Path) -> None:
    package_root, manifest_path = _workspace_bundle(tmp_path)
    (package_root / "dbfox.workspace.dbfox-dlc").write_bytes(b"tampered")
    storage_root = tmp_path / "installed"

    with pytest.raises(RuntimeError, match="digest mismatch"):
        bootstrap_system_dlcs(
            storage_root,
            package_root,
            manifest_path=manifest_path,
        )

    assert InstalledDlcRegistry(storage_root).list_installed_dlcs() == []


def test_runtime_compiles_bootstrapped_workspace_through_installed_snapshot(
    tmp_path: Path,
) -> None:
    package_root, manifest_path = _workspace_bundle(tmp_path)
    storage_root = tmp_path / "installed"
    try:
        snapshot = initialize_runtime_snapshot(
            storage_root,
            system_dlc_dir=package_root,
            system_dlc_manifest=manifest_path,
        )
    finally:
        set_active_runtime_snapshot(None)

    assert [item.dlc_id for item in snapshot.active_dlcs] == ["dbfox.workspace"]
    assert snapshot.activation_failures == ()


def test_host_trust_roots_extend_persisted_user_publishers(tmp_path: Path) -> None:
    host_key = ed25519.Ed25519PrivateKey.generate().public_key()
    user_key = ed25519.Ed25519PrivateKey.generate().public_key()
    persistent = DlcTrustStore(storage_root=tmp_path)
    user_fingerprint = persistent.add_trusted_key(public_key_to_base64(user_key))

    combined = DlcTrustStore(
        trusted_keys={"host": public_key_to_base64(host_key)},
        storage_root=tmp_path,
    )

    assert combined.is_trusted(user_fingerprint)
    assert len(combined.load()) == 2


def test_release_builder_emits_exact_first_party_capability_package_pins(
    tmp_path: Path,
) -> None:
    private_key = ed25519.Ed25519PrivateKey.generate()
    key_path = tmp_path / "release-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    output_dir = tmp_path / "system-dlcs"
    manifest_path = build_system_dlc_bundle(output_dir, key_path)
    manifest = SystemDlcBundleManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

    assert manifest.development is False
    assert [item.dlc_id for item in manifest.packages] == [
        "dbfox.data",
        "dbfox.workspace",
        "dbfox.music",
        "dbfox.visualization",
    ]
    assert [item.default_enabled for item in manifest.packages] == [True, True, True, True]
    assert all((output_dir / item.filename).is_file() for item in manifest.packages)

    storage_root = tmp_path / "installed-release-bundle"
    try:
        snapshot = initialize_runtime_snapshot(
            storage_root,
            system_dlc_dir=output_dir,
            system_dlc_manifest=manifest_path,
        )
    finally:
        set_active_runtime_snapshot(None)

    installed = {
        item.dlc_id: item
        for item in InstalledDlcRegistry(storage_root).list_installed_dlcs()
    }
    assert installed["dbfox.data"].desired_enabled is True
    assert installed["dbfox.workspace"].desired_enabled is True
    assert installed["dbfox.music"].desired_enabled is True
    assert installed["dbfox.visualization"].desired_enabled is True
    assert [item.dlc_id for item in snapshot.active_dlcs] == [
        "dbfox.data",
        "dbfox.music",
        "dbfox.visualization",
        "dbfox.workspace",
    ]
    assert snapshot.activation_failures == ()
    assert "sql_validate" in {item.tool.name for item in snapshot.tools}
    assert "file_read" in {item.tool.name for item in snapshot.tools}
    assert "music_compose_piano" in {item.tool.name for item in snapshot.tools}
    assert "visualization_create" in {item.tool.name for item in snapshot.tools}
