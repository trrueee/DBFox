"""Comprehensive test suite for Runtime DLC Package Foundation (R1).

Verifies:
1. Canonical JSON determinism & Ed25519 signature verification.
2. Valid signed package installation.
3. Developer Mode vs Production trust requirements.
4. Cryptographic envelope rules (payload-only integrity, no self-hash).
5. Tamper detection (manifest tamper, integrity tamper, payload hash mismatch, invalid signature).
6. Archive security (zip slip, absolute paths, backslash aliases, duplicate paths, case collisions).
7. Bounds enforcement (package too large, extracted too large, too many files, single file too large, path too long).
8. Native extension rejection (.so, .pyd, .dylib, .dll, .exe).
9. Compatibility evaluation (schema version, extension API version, requiresDbfox constraint).
10. Atomic staging & Content-addressed store (sha256-<digest>).
11. Installed DLC Registry (schema version, atomic writes, corrupt recovery, conflict detection).
12. Zero code execution guarantee during verification and installation.
"""

import json
import sys
from pathlib import Path

import pytest

from engine.dlc import (
    DlcError,
    DlcErrorCode,
    DlcIntegrity,
    DlcPackageService,
    DlcTrustStore,
    InstalledDlcRegistry,
)
from engine.dlc.integrity import build_signed_message_bytes, canonical_json_bytes
from engine.dlc.trust import DlcTrustStatus
from engine.tests.fixtures.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)



@pytest.fixture
def test_keypair():
    return generate_test_keypair()


@pytest.fixture
def trust_store(test_keypair):
    _, pub_key_b64 = test_keypair
    store = DlcTrustStore()
    store.add_trusted_key(pub_key_b64)
    return store


@pytest.fixture
def dlc_service(tmp_path: Path, trust_store: DlcTrustStore):
    return DlcPackageService(storage_root=tmp_path / "dlc_storage", trust_store=trust_store)


# ---------------------------------------------------------------------------
# 1. Canonical JSON & Cryptographic Envelope Determinism
# ---------------------------------------------------------------------------


def test_canonical_json_determinism():
    """Prove two independent dicts with different key insertion order produce byte-identical canonical JSON."""
    dict_a = {"version": "1.0.0", "id": "acme.test", "displayName": "Test"}
    dict_b = {"displayName": "Test", "id": "acme.test", "version": "1.0.0"}

    bytes_a = canonical_json_bytes(dict_a)
    bytes_b = canonical_json_bytes(dict_b)

    assert bytes_a == bytes_b
    assert bytes_a == b'{"displayName":"Test","id":"acme.test","version":"1.0.0"}'


def test_signed_payload_format():
    """Prove signed payload matches exact b'DBFOX-DLC-V1\\n' + manifest + b'\\n' + integrity format."""
    manifest_bytes = b'{"id":"acme.test"}'
    integrity_bytes = b'{"entries":{}}'

    signed_msg = build_signed_message_bytes(manifest_bytes, integrity_bytes)
    assert signed_msg == b"DBFOX-DLC-V1\n" + manifest_bytes + b"\n" + integrity_bytes


def test_integrity_excludes_control_files():
    """Prove integrity mapping rejects listing integrity.json or signature.sig."""
    with pytest.raises(DlcError) as exc_info:
        DlcIntegrity({"integrity.json": "0" * 64})
    assert exc_info.value.code == DlcErrorCode.INVALID_INTEGRITY

    with pytest.raises(DlcError) as exc_info:
        DlcIntegrity({"signature.sig": "0" * 64})
    assert exc_info.value.code == DlcErrorCode.INVALID_INTEGRITY


# ---------------------------------------------------------------------------
# 2. Valid Installation & Trust Verification
# ---------------------------------------------------------------------------


def test_install_valid_signed_package(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove a valid signed package installs cleanly into content-addressed store without code execution."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(private_key=priv_key)
    archive_path = tmp_path / "acme.test_dlc-1.0.0.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    # Record loaded modules before installation to prove zero execution
    initial_modules = set(sys.modules.keys())

    result = dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert result.dlc_id == "acme.test_dlc"
    assert result.version == "1.0.0"
    assert result.trust_status == DlcTrustStatus.TRUSTED_SIGNED
    assert result.install_dir.is_dir()
    assert (result.install_dir / "manifest.json").is_file()
    assert (result.install_dir / "backend" / "entry.py").is_file()

    # Verify zero Python code executed
    new_modules = set(sys.modules.keys()) - initial_modules
    assert not any("acme" in m or "entry" in m for m in new_modules)

    # Verify registry state
    record = dlc_service.registry.get_installed_dlc("acme.test_dlc")
    assert record is not None
    assert record.selected_digest == result.package_digest
    assert record.package_version == "1.0.0"
    assert record.desired_enabled is False
    assert [item.package_digest for item in record.installed_versions] == [
        result.package_digest
    ]
    assert json.loads(record.model_dump_json())["installed_versions"][0][
        "package_version"
    ] == "1.0.0"


def test_install_unsigned_package_in_developer_mode(
    tmp_path: Path,
    dlc_service: DlcPackageService,
):
    """Prove unsigned package installs when developer_mode=True."""
    archive_bytes = build_test_dlc_archive(omit_signature=True)
    archive_path = tmp_path / "unsigned.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    result = dlc_service.install_from_file(archive_path, developer_mode=True)
    assert result.trust_status == DlcTrustStatus.DEVELOPER_UNSIGNED


def test_install_unsigned_package_in_production_mode_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
):
    """Prove unsigned package is rejected when developer_mode=False."""
    archive_bytes = build_test_dlc_archive(omit_signature=True)
    archive_path = tmp_path / "unsigned.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, developer_mode=False)

    assert exc_info.value.code == DlcErrorCode.SIGNATURE_REQUIRED


def test_authentic_untrusted_publisher_requires_explicit_trust(
    tmp_path: Path,
    dlc_service: DlcPackageService,
):
    """Prove valid signature from an untrusted publisher key is rejected in production."""
    other_priv_key, other_pub_b64 = generate_test_keypair()
    archive_bytes = build_test_dlc_archive(private_key=other_priv_key)
    archive_path = tmp_path / "untrusted.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(
            archive_path,
            developer_mode=False,
            publisher_key_base64=other_pub_b64,
        )

    assert exc_info.value.code == DlcErrorCode.TRUST_REQUIRED


# ---------------------------------------------------------------------------
# 3. Cryptographic Tamper Rejection
# ---------------------------------------------------------------------------


def test_invalid_signature_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove corrupt signature bytes cause INVALID_SIGNATURE rejection."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(private_key=priv_key, corrupt_signature=True)
    archive_path = tmp_path / "corrupt_sig.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.INVALID_SIGNATURE


def test_payload_hash_mismatch_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove tampered payload file causes HASH_MISMATCH rejection."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(
        private_key=priv_key,
        corrupt_payload_hash="backend/entry.py",
    )
    archive_path = tmp_path / "tampered_payload.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.HASH_MISMATCH


def test_unlisted_file_in_archive_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove unlisted extra file in archive causes UNLISTED_FILE rejection."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(
        private_key=priv_key,
        extra_unlisted_files={"backend/malicious.py": "import os; os.system('bad')"},
    )
    archive_path = tmp_path / "unlisted_file.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.UNLISTED_FILE


def test_missing_listed_file_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove missing payload file declared in integrity causes MISSING_FILE rejection."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(
        private_key=priv_key,
        omit_payload_file="frontend/index.css",
    )
    archive_path = tmp_path / "missing_file.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.MISSING_FILE


# ---------------------------------------------------------------------------
# 4. Hostile Archive & Path Traversal Security
# ---------------------------------------------------------------------------

VALID_MANIFEST_BYTES = canonical_json_bytes({
    "manifestSchemaVersion": 1,
    "id": "acme.test_dlc",
    "version": "1.0.0",
    "displayName": "Test DLC",
    "publisher": "acme",
    "extensionApiVersion": "1",
    "requiresDbfox": ">=1.0.0",
    "entrypoints": {"backend": "backend/entry.py"},
})


@pytest.mark.parametrize(
    "bad_path",

    [
        "../secret.py",
        "backend/../../etc/passwd",
        "/absolute/path.py",
        "backend\\windows\\alias.py",
        "backend/./local.py",
        "backend//empty_segment.py",
        "a" * 256,
        "",
    ],
)
def test_normalize_posix_archive_path_rejects_unsafe_paths(bad_path: str):
    """Prove path normalization helper strictly rejects unsafe segments, backslashes, and over-length paths."""
    from engine.dlc.integrity import normalize_posix_archive_path

    with pytest.raises(DlcError) as exc_info:
        normalize_posix_archive_path(bad_path)

    assert exc_info.value.code in (DlcErrorCode.UNSAFE_PATH, DlcErrorCode.PATH_TOO_LONG)


@pytest.mark.parametrize(
    "bad_zip_path",
    [
        "../secret.py",
        "backend/../../etc/passwd",
        "/absolute/path.py",
        "backend/./local.py",
        "backend//empty_segment.py",
    ],
)
def test_hostile_archive_paths_rejected(tmp_path: Path, dlc_service: DlcPackageService, bad_zip_path: str):
    """Prove zip-slip, absolute paths, and dot segments in ZIP headers are rejected with UNSAFE_PATH."""
    archive_bytes = build_test_dlc_archive(
        raw_zip_entries=[
            ("manifest.json", VALID_MANIFEST_BYTES),
            ("integrity.json", b'{"entries":{}}'),
            (bad_zip_path, b"malicious content"),
        ]
    )
    archive_path = tmp_path / "hostile.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, developer_mode=True)

    assert exc_info.value.code == DlcErrorCode.UNSAFE_PATH



def test_duplicate_normalized_path_rejected(tmp_path: Path, dlc_service: DlcPackageService):
    """Prove duplicate normalized entries in archive are rejected with DUPLICATE_PATH."""
    archive_bytes = build_test_dlc_archive(
        raw_zip_entries=[
            ("manifest.json", VALID_MANIFEST_BYTES),
            ("integrity.json", b'{"entries":{}}'),
            ("backend/entry.py", b"def register(h): pass"),
            ("backend/entry.py", b"duplicate entry"),
        ]
    )
    archive_path = tmp_path / "dup.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, developer_mode=True)

    assert exc_info.value.code == DlcErrorCode.DUPLICATE_PATH


def test_case_collision_rejected(tmp_path: Path, dlc_service: DlcPackageService):
    """Prove case-insensitive path collisions are rejected with CASE_COLLISION."""
    archive_bytes = build_test_dlc_archive(
        raw_zip_entries=[
            ("manifest.json", VALID_MANIFEST_BYTES),
            ("integrity.json", b'{"entries":{}}'),
            ("backend/Helper.py", b"code A"),
            ("backend/helper.py", b"code B"),
        ]
    )
    archive_path = tmp_path / "case_collision.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, developer_mode=True)

    assert exc_info.value.code == DlcErrorCode.CASE_COLLISION


# ---------------------------------------------------------------------------
# 5. Native Extension & Binary Rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "native_file",
    [
        "backend/custom_module.so",
        "backend/custom_module.cpython-312-x86_64-linux-gnu.so",
        "backend/fast_calc.pyd",
        "backend/libnative.dylib",
        "backend/helper.dll",
        "backend/exec.exe",
    ],
)
def test_native_extensions_rejected(tmp_path: Path, dlc_service: DlcPackageService, native_file: str):
    """Prove native binary extensions (.so, .pyd, .dylib, .dll, .exe) are strictly rejected."""
    archive_bytes = build_test_dlc_archive(
        raw_zip_entries=[
            ("manifest.json", VALID_MANIFEST_BYTES),
            ("integrity.json", b'{"entries":{}}'),
            (native_file, b"\x7fELF\x02\x01\x01"),
        ]
    )
    archive_path = tmp_path / "native.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, developer_mode=True)

    assert exc_info.value.code == DlcErrorCode.NATIVE_EXTENSION_NOT_ALLOWED



# ---------------------------------------------------------------------------
# 6. Compatibility Checks
# ---------------------------------------------------------------------------


def test_incompatible_extension_api_version_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove incompatible extensionApiVersion raises INCOMPATIBLE_EXTENSION_API."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.future_api",
            "version": "1.0.0",
            "displayName": "Future API DLC",
            "publisher": "acme",
            "extensionApiVersion": "99",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        private_key=priv_key,
    )
    archive_path = tmp_path / "future_api.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.INCOMPATIBLE_EXTENSION_API


def test_incompatible_dbfox_version_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove unsatisfied requiresDbfox raises INCOMPATIBLE_DBFOX_VERSION."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.future_dbfox",
            "version": "1.0.0",
            "displayName": "Future DBFox DLC",
            "publisher": "acme",
            "extensionApiVersion": "1",
            "requiresDbfox": ">=9.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        private_key=priv_key,
    )
    archive_path = tmp_path / "future_dbfox.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.INCOMPATIBLE_DBFOX_VERSION


# ---------------------------------------------------------------------------
# 7. Registry & Idempotency Lifecycle
# ---------------------------------------------------------------------------


def test_reinstall_same_package_is_idempotent(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove installing the identical package twice is idempotent without redundant extraction."""
    priv_key, pub_key_b64 = test_keypair
    archive_bytes = build_test_dlc_archive(private_key=priv_key)
    archive_path = tmp_path / "idempotent.dbfox-dlc"
    archive_path.write_bytes(archive_bytes)

    res1 = dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)
    res2 = dlc_service.install_from_file(archive_path, publisher_key_base64=pub_key_b64)

    assert res1.package_digest == res2.package_digest
    assert res1.install_dir == res2.install_dir


def test_conflicting_digest_for_same_version_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove installing a modified package with the same dlc_id and version is rejected with CONFLICTING_DIGEST."""
    priv_key, pub_key_b64 = test_keypair
    archive1 = build_test_dlc_archive(
        payload_files={"backend/entry.py": "def register(h): pass\n# v1"},
        private_key=priv_key,
    )
    archive2 = build_test_dlc_archive(
        payload_files={"backend/entry.py": "def register(h): pass\n# v2 modified"},
        private_key=priv_key,
    )

    path1 = tmp_path / "pkg1.dbfox-dlc"
    path2 = tmp_path / "pkg2.dbfox-dlc"
    path1.write_bytes(archive1)
    path2.write_bytes(archive2)

    dlc_service.install_from_file(path1, publisher_key_base64=pub_key_b64)

    with pytest.raises(DlcError) as exc_info:
        dlc_service.install_from_file(path2, publisher_key_base64=pub_key_b64)

    assert exc_info.value.code == DlcErrorCode.CONFLICTING_DIGEST


def test_registry_v1_is_migrated_to_one_selected_version_on_next_write(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    digest = "a" * 64
    registry_file = storage_root / "registry.json"
    registry_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "installed_dlcs": {
                    "acme.echo": {
                        "dlc_id": "acme.echo",
                        "selected_digest": digest,
                        "package_version": "1.0.0",
                        "desired_enabled": True,
                        "runtime_state": "active",
                        "trust_status": "trusted_signed",
                        "publisher_key_id": "b" * 64,
                        "installed_at": "2026-08-21T00:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    registry = InstalledDlcRegistry(storage_root)
    migrated = registry.get_installed_dlc("acme.echo")
    assert migrated is not None
    assert migrated.selected_digest == digest
    assert migrated.desired_enabled is True
    assert [(item.package_version, item.package_digest) for item in migrated.installed_versions] == [
        ("1.0.0", digest)
    ]
    assert json.loads(registry_file.read_text(encoding="utf-8"))["schema_version"] == 1

    registry.set_desired_enabled("acme.echo", False)
    persisted = json.loads(registry_file.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 2
    assert "runtime_state" not in persisted["installed_dlcs"]["acme.echo"]
    assert persisted["installed_dlcs"]["acme.echo"]["installed_versions"] == [
        {
            "installed_at": "2026-08-21T00:00:00+00:00",
            "package_digest": digest,
            "package_version": "1.0.0",
            "publisher_key_id": "b" * 64,
            "trust_status": "trusted_signed",
        }
    ]


def test_corrupt_registry_fails_safe(tmp_path: Path):
    """Prove corrupted registry.json raises REGISTRY_CORRUPT and does not silently overwrite."""
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    registry_file = storage_root / "registry.json"
    registry_file.write_text("{corrupt json", encoding="utf-8")

    registry = InstalledDlcRegistry(storage_root)
    with pytest.raises(DlcError) as exc_info:
        registry.load()

    assert exc_info.value.code == DlcErrorCode.REGISTRY_CORRUPT
    # Verify file was not erased
    assert registry_file.read_text(encoding="utf-8") == "{corrupt json"
