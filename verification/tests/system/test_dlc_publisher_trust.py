"""R4.0 single-file publisher authenticity and durable trust contracts."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

from engine.dlc import (
    BuiltinContributionSet,
    ContributionCompiler,
    DlcError,
    DlcErrorCode,
    DlcIntegrity,
    DlcManifest,
    DlcPackageService,
    DlcTrustStore,
)
from engine.dlc.integrity import build_signed_message_bytes, canonical_json_bytes
from engine.dlc.trust import (
    MAX_TRUSTED_PUBLISHERS,
    DlcTrustStatus,
    compute_key_fingerprint,
    public_key_from_base64,
)
from verification.testkit.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)


def _v2_manifest(public_key_base64: str, *, dlc_id: str = "acme.echo") -> dict[str, object]:
    return {
        "manifestSchemaVersion": 2,
        "id": dlc_id,
        "version": "1.0.0",
        "displayName": "Acme Echo",
        "publisher": "acme",
        "publisherKey": public_key_base64,
        "description": "R4 publisher trust fixture",
        "extensionApiVersion": "2",
        "requiresDbfox": ">=1.0.0",
        "entrypoints": {
            "backend": "backend/entry.py",
            "frontend": "frontend/index.js",
        },
        "permissions": [],
    }


def _write_v2_archive(
    path: Path,
    *,
    private_key,
    public_key_base64: str,
    corrupt_signature: bool = False,
    dlc_id: str = "acme.echo",
) -> bytes:
    archive_bytes = build_test_dlc_archive(
        manifest_data=_v2_manifest(public_key_base64, dlc_id=dlc_id),
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host):\n    pass\n",
            "frontend/index.js": "export function register(host) {}\n",
        },
        private_key=private_key,
        corrupt_signature=corrupt_signature,
    )
    path.write_bytes(archive_bytes)
    return archive_bytes


def test_v2_unknown_publisher_is_authentic_but_requires_trust(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "acme.echo.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")

    inspection = service.inspect_from_file(archive_path)

    assert inspection.trust_status == DlcTrustStatus.UNTRUSTED
    assert inspection.publisher_key_base64 == public_key_base64
    assert inspection.publisher_key_id == compute_key_fingerprint(
        public_key_from_base64(public_key_base64)
    )
    with pytest.raises(DlcError) as exc_info:
        service.install_from_file(archive_path)
    assert exc_info.value.code == DlcErrorCode.TRUST_REQUIRED
    assert exc_info.value.details["package_digest"] == inspection.package_digest
    assert exc_info.value.details["publisher_key_id"] == inspection.publisher_key_id
    with pytest.raises(DlcError) as developer_exc_info:
        service.install_from_file(archive_path, developer_mode=True)
    assert developer_exc_info.value.code == DlcErrorCode.TRUST_REQUIRED


def test_v2_unsigned_package_cannot_use_developer_mode_bypass(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "unsigned-v2.dbfox-dlc"
    archive_path.write_bytes(
        build_test_dlc_archive(
            manifest_data=_v2_manifest(public_key_base64),
            private_key=private_key,
            omit_signature=True,
        )
    )

    with pytest.raises(DlcError) as exc_info:
        DlcPackageService(tmp_path / "runtime" / "dlcs").install_from_file(
            archive_path,
            developer_mode=True,
        )
    assert exc_info.value.code == DlcErrorCode.SIGNATURE_REQUIRED


def test_trust_then_single_file_install_survives_service_rebuild_and_restart(
    tmp_path: Path,
) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "acme.echo.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    first_service = DlcPackageService(storage_root)
    inspection = first_service.inspect_from_file(archive_path)

    trusted_fingerprint = first_service.trust_publisher_from_file(
        archive_path,
        expected_package_digest=inspection.package_digest,
        expected_publisher_key_id=inspection.publisher_key_id or "",
    )

    trust_payload = json.loads(
        (storage_root / "trusted_publishers.json").read_text(encoding="utf-8")
    )
    assert trust_payload == {
        "schema_version": 1,
        "trusted_publishers": {trusted_fingerprint: public_key_base64},
    }

    rebuilt_service = DlcPackageService(storage_root)
    initial_modules = set(sys.modules)
    result = rebuilt_service.install_from_file(archive_path)
    assert result.trust_status == DlcTrustStatus.TRUSTED_SIGNED
    assert result.publisher_key_id == trusted_fingerprint
    assert not any(
        module_name.startswith("_dbfox_dlc_acme_echo")
        for module_name in set(sys.modules) - initial_modules
    )

    rebuilt_service.registry.set_desired_enabled(result.dlc_id, True)
    snapshot = ContributionCompiler(storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert [identity.dlc_id for identity in snapshot.active_dlcs] == ["acme.echo"]
    assert snapshot.activation_failures == ()


def test_restart_reverify_rejects_valid_but_different_embedded_key(
    tmp_path: Path,
) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "restart-key-mismatch.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    service = DlcPackageService(storage_root)
    inspection = service.inspect_from_file(archive_path)
    service.trust_publisher_from_file(
        archive_path,
        expected_package_digest=inspection.package_digest,
        expected_publisher_key_id=inspection.publisher_key_id or "",
    )
    result = service.install_from_file(archive_path)
    service.registry.set_desired_enabled(result.dlc_id, True)

    replacement_private_key, replacement_public_key = generate_test_keypair()
    service.trust_store.add_trusted_key(replacement_public_key)
    manifest_file = result.install_dir / "manifest.json"
    integrity_file = result.install_dir / "integrity.json"
    signature_file = result.install_dir / "signature.sig"
    manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_payload["publisherKey"] = replacement_public_key
    canonical_manifest = canonical_json_bytes(manifest_payload)
    integrity = DlcIntegrity.from_bytes(integrity_file.read_bytes())
    replacement_signature = replacement_private_key.sign(
        build_signed_message_bytes(canonical_manifest, integrity.canonical_bytes())
    )
    manifest_file.write_bytes(canonical_manifest)
    signature_file.write_text(
        base64.b64encode(replacement_signature).decode("ascii"),
        encoding="ascii",
    )

    snapshot = ContributionCompiler(storage_root).compile(
        built_ins=BuiltinContributionSet()
    )
    assert snapshot.active_dlcs == ()
    assert [failure.error_code for failure in snapshot.activation_failures] == [
        DlcErrorCode.PUBLISHER_KEY_MISMATCH.value
    ]


def test_v2_embedded_key_must_verify_the_signature(tmp_path: Path) -> None:
    signing_key, _signing_public_key = generate_test_keypair()
    _other_key, embedded_public_key = generate_test_keypair()
    archive_path = tmp_path / "key-mismatch.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=signing_key,
        public_key_base64=embedded_public_key,
    )

    with pytest.raises(DlcError) as exc_info:
        DlcPackageService(tmp_path / "runtime" / "dlcs").inspect_from_file(archive_path)
    assert exc_info.value.code == DlcErrorCode.INVALID_SIGNATURE


def test_v2_rejects_conflicting_external_key_parameter(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    _other_private_key, other_public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "external-key.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    service = DlcPackageService(tmp_path / "runtime" / "dlcs")

    with pytest.raises(DlcError) as exc_info:
        service.install_from_file(
            archive_path,
            publisher_key_base64=other_public_key_base64,
        )
    assert exc_info.value.code == DlcErrorCode.PUBLISHER_KEY_MISMATCH


def test_tamper_between_inspect_and_trust_does_not_persist_key(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "tampered-before-trust.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    service = DlcPackageService(storage_root)
    inspection = service.inspect_from_file(archive_path)

    archive_path.write_bytes(
        build_test_dlc_archive(
            manifest_data=_v2_manifest(public_key_base64),
            payload_files={
                "backend/entry.py": "def register(host):\n    changed = True\n",
                "frontend/index.js": "export function register(host) {}\n",
            },
            private_key=private_key,
        )
    )

    with pytest.raises(DlcError) as exc_info:
        service.trust_publisher_from_file(
            archive_path,
            expected_package_digest=inspection.package_digest,
            expected_publisher_key_id=inspection.publisher_key_id or "",
        )
    assert exc_info.value.code == DlcErrorCode.PACKAGE_TAMPERED
    assert not (storage_root / "trusted_publishers.json").exists()


def test_invalid_signature_before_trust_does_not_persist_key(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "invalid-before-trust.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    service = DlcPackageService(storage_root)
    inspection = service.inspect_from_file(archive_path)
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
        corrupt_signature=True,
    )

    with pytest.raises(DlcError) as exc_info:
        service.trust_publisher_from_file(
            archive_path,
            expected_package_digest=inspection.package_digest,
            expected_publisher_key_id=inspection.publisher_key_id or "",
        )
    assert exc_info.value.code == DlcErrorCode.INVALID_SIGNATURE
    assert not (storage_root / "trusted_publishers.json").exists()


def test_trust_rejects_ui_supplied_fingerprint_mismatch(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "fingerprint-mismatch.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    service = DlcPackageService(storage_root)
    inspection = service.inspect_from_file(archive_path)

    with pytest.raises(DlcError) as exc_info:
        service.trust_publisher_from_file(
            archive_path,
            expected_package_digest=inspection.package_digest,
            expected_publisher_key_id="0" * 64,
        )
    assert exc_info.value.code == DlcErrorCode.PUBLISHER_KEY_MISMATCH
    assert not (storage_root / "trusted_publishers.json").exists()


def test_publisher_display_text_does_not_participate_in_trust(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    manifest = _v2_manifest(public_key_base64, dlc_id="renamed.echo")
    manifest["publisher"] = "renamed.publisher"
    archive_path = tmp_path / "renamed.dbfox-dlc"
    archive_path.write_bytes(
        build_test_dlc_archive(manifest_data=manifest, private_key=private_key)
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    service = DlcPackageService(storage_root)
    inspection = service.inspect_from_file(archive_path)
    service.trust_publisher_from_file(
        archive_path,
        expected_package_digest=inspection.package_digest,
        expected_publisher_key_id=inspection.publisher_key_id or "",
    )

    result = DlcPackageService(storage_root).install_from_file(archive_path)
    assert result.publisher_key_id == inspection.publisher_key_id
    assert result.trust_status == DlcTrustStatus.TRUSTED_SIGNED


def test_corrupt_trust_store_fails_closed_without_overwrite(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "corrupt-store.dbfox-dlc"
    _write_v2_archive(
        archive_path,
        private_key=private_key,
        public_key_base64=public_key_base64,
    )
    storage_root = tmp_path / "runtime" / "dlcs"
    storage_root.mkdir(parents=True)
    trust_store_file = storage_root / "trusted_publishers.json"
    trust_store_file.write_text('{"schema_version":1,"trusted_publishers":"bad"}', encoding="utf-8")
    service = DlcPackageService(storage_root)

    with pytest.raises(DlcError) as exc_info:
        service.inspect_from_file(archive_path)
    assert exc_info.value.code == DlcErrorCode.TRUST_STORE_CORRUPT
    with pytest.raises(DlcError) as trust_exc_info:
        service.trust_store.add_trusted_key(public_key_base64)
    assert trust_exc_info.value.code == DlcErrorCode.TRUST_STORE_CORRUPT
    assert trust_store_file.read_text(encoding="utf-8") == (
        '{"schema_version":1,"trusted_publishers":"bad"}'
    )


def test_trust_store_rejects_metadata_and_fingerprint_key_mismatch(tmp_path: Path) -> None:
    _private_key, public_key_base64 = generate_test_keypair()
    fingerprint = compute_key_fingerprint(public_key_from_base64(public_key_base64))
    storage_root = tmp_path / "runtime" / "dlcs"
    storage_root.mkdir(parents=True)
    trust_store_file = storage_root / "trusted_publishers.json"
    invalid_payloads = (
        {
            "schema_version": 1,
            "trusted_publishers": {fingerprint: public_key_base64},
            "publisher_metadata": {"name": "must-not-be-stored"},
        },
        {
            "schema_version": 1,
            "trusted_publishers": {"0" * 64: public_key_base64},
        },
    )

    for invalid_payload in invalid_payloads:
        serialized = json.dumps(invalid_payload, separators=(",", ":"))
        trust_store_file.write_text(serialized, encoding="utf-8")
        with pytest.raises(DlcError) as exc_info:
            DlcTrustStore(storage_root=storage_root).load()
        assert exc_info.value.code == DlcErrorCode.TRUST_STORE_CORRUPT
        assert trust_store_file.read_text(encoding="utf-8") == serialized


def test_trust_store_enforces_bounded_publisher_count() -> None:
    trusted_keys = {
        str(index): generate_test_keypair()[1]
        for index in range(MAX_TRUSTED_PUBLISHERS)
    }
    store = DlcTrustStore(trusted_keys)
    _extra_private_key, extra_public_key = generate_test_keypair()

    with pytest.raises(DlcError) as exc_info:
        store.add_trusted_key(extra_public_key)
    assert exc_info.value.code == DlcErrorCode.TRUST_STORE_FULL


def test_v1_requires_explicit_external_key_compatibility_path(tmp_path: Path) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    archive_path = tmp_path / "legacy-v1.dbfox-dlc"
    archive_path.write_bytes(build_test_dlc_archive(private_key=private_key))
    storage_root = tmp_path / "runtime" / "dlcs"
    service = DlcPackageService(storage_root)
    service.trust_store.add_trusted_key(public_key_base64)

    with pytest.raises(DlcError) as exc_info:
        service.install_from_file(archive_path)
    assert exc_info.value.code == DlcErrorCode.SIGNATURE_REQUIRED

    result = service.install_from_file(
        archive_path,
        publisher_key_base64=public_key_base64,
    )
    assert result.trust_status == DlcTrustStatus.TRUSTED_SIGNED


@pytest.mark.parametrize(
    "publisher_key",
    ["not-base64", "QQ==", " AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="],
)
def test_v2_manifest_rejects_noncanonical_or_wrong_length_keys(
    publisher_key: str,
) -> None:
    with pytest.raises(DlcError) as exc_info:
        DlcManifest.from_bytes(
            json.dumps(_v2_manifest(publisher_key)).encode("utf-8")
        )
    assert exc_info.value.code == DlcErrorCode.INVALID_MANIFEST
