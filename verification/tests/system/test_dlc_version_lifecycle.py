"""R6 side-by-side package selection and rollback safety contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.dlc import (
    BuiltinContributionSet,
    ContributionCompiler,
    DlcError,
    DlcErrorCode,
    DlcPackageService,
    DlcTrustStore,
)
from engine.dlc.registry import (
    MAX_INSTALLED_VERSIONS_PER_DLC,
    InstalledDlcRegistry,
    InstalledDlcVersion,
)
from verification.testkit.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)


def _write_version(
    path: Path,
    *,
    version: str,
    private_key,
    public_key_base64: str,
    entrypoint: str,
) -> None:
    path.write_bytes(
        build_test_dlc_archive(
            manifest_data={
                "manifestSchemaVersion": 2,
                "id": "acme.versioned",
                "version": version,
                "displayName": "Acme Versioned",
                "publisher": "acme",
                "publisherKey": public_key_base64,
                "extensionApiVersion": "2",
                "requiresDbfox": ">=1.0.0",
                "entrypoints": {
                    "backend": "backend/entry.py",
                    "frontend": "frontend/index.js",
                },
            },
            payload_files={
                "backend/__init__.py": "",
                "backend/entry.py": entrypoint,
                "frontend/index.js": "export function register() {}\n",
            },
            private_key=private_key,
        )
    )


def _compile(compiler: ContributionCompiler):
    return compiler.compile(built_ins=BuiltinContributionSet())


def test_rollback_switches_only_package_digest_and_keeps_current_dlc_data(
    tmp_path: Path,
) -> None:
    private_key, public_key_base64 = generate_test_keypair()
    v1_path = tmp_path / "acme.versioned-1.0.0.dbfox-dlc"
    v2_path = tmp_path / "acme.versioned-2.0.0.dbfox-dlc"
    _write_version(
        v1_path,
        version="1.0.0",
        private_key=private_key,
        public_key_base64=public_key_base64,
        entrypoint=(
            "def register(host):\n"
            "    if (host.runtime_info.data_path / 'schema-v2').exists():\n"
            "        raise RuntimeError('package v1 cannot read schema v2')\n"
        ),
    )
    _write_version(
        v2_path,
        version="2.0.0",
        private_key=private_key,
        public_key_base64=public_key_base64,
        entrypoint="def register(host):\n    pass\n",
    )

    storage_root = tmp_path / "runtime" / "dlcs"
    trust_store = DlcTrustStore(storage_root=storage_root)
    trust_store.add_trusted_key(public_key_base64)
    service = DlcPackageService(storage_root, trust_store=trust_store)
    compiler = ContributionCompiler(storage_root, trust_store=trust_store)

    v1 = service.install_from_file(v1_path)
    service.set_desired_enabled("acme.versioned", True)
    active_v1 = _compile(compiler)
    assert [(item.package_version, item.package_digest) for item in active_v1.active_dlcs] == [
        ("1.0.0", v1.package_digest)
    ]

    v2 = service.install_from_file(v2_path)
    after_install = service.registry.get_installed_dlc("acme.versioned")
    assert after_install is not None
    assert after_install.selected_digest == v1.package_digest
    assert [item.package_digest for item in after_install.installed_versions] == [
        v1.package_digest,
        v2.package_digest,
    ]
    assert active_v1.active_dlcs[0].package_digest == v1.package_digest

    service.select_package("acme.versioned", v2.package_digest)
    active_v2 = _compile(compiler)
    assert [(item.package_version, item.package_digest) for item in active_v2.active_dlcs] == [
        ("2.0.0", v2.package_digest)
    ]

    schema_marker = storage_root / "data" / "acme.versioned" / "schema-v2"
    schema_marker.write_text("current", encoding="utf-8")
    service.select_package("acme.versioned", v1.package_digest)
    failed_rollback = _compile(compiler)

    assert failed_rollback.active_dlcs == ()
    assert len(failed_rollback.activation_failures) == 1
    assert failed_rollback.activation_failures[0].dlc_id == "acme.versioned"
    assert "package v1 cannot read schema v2" in failed_rollback.activation_failures[0].message
    assert schema_marker.read_text(encoding="utf-8") == "current"
    assert service.store.get_package_dir(v1.package_digest).is_dir()
    assert service.store.get_package_dir(v2.package_digest).is_dir()
    assert not list(service.store.get_package_dir(v1.package_digest).rglob("__pycache__"))
    assert not list(service.store.get_package_dir(v2.package_digest).rglob("__pycache__"))


def test_new_version_cannot_change_the_installed_dlc_publisher_key(
    tmp_path: Path,
) -> None:
    first_key, first_public_key = generate_test_keypair()
    second_key, second_public_key = generate_test_keypair()
    v1_path = tmp_path / "acme.versioned-1.0.0.dbfox-dlc"
    takeover_path = tmp_path / "acme.versioned-2.0.0.dbfox-dlc"
    _write_version(
        v1_path,
        version="1.0.0",
        private_key=first_key,
        public_key_base64=first_public_key,
        entrypoint="def register(host):\n    pass\n",
    )
    _write_version(
        takeover_path,
        version="2.0.0",
        private_key=second_key,
        public_key_base64=second_public_key,
        entrypoint="def register(host):\n    pass\n",
    )

    storage_root = tmp_path / "runtime" / "dlcs"
    trust_store = DlcTrustStore(storage_root=storage_root)
    trust_store.add_trusted_key(first_public_key)
    trust_store.add_trusted_key(second_public_key)
    service = DlcPackageService(storage_root, trust_store=trust_store)
    service.install_from_file(v1_path)
    takeover = service.inspect_from_file(takeover_path)

    with pytest.raises(DlcError) as exc_info:
        service.install_from_file(takeover_path)

    assert exc_info.value.code == DlcErrorCode.PUBLISHER_KEY_MISMATCH
    record = service.registry.get_installed_dlc("acme.versioned")
    assert record is not None
    assert [item.package_version for item in record.installed_versions] == ["1.0.0"]
    assert not service.store.get_package_dir(takeover.package_digest).exists()


def test_registry_requires_explicit_cleanup_at_the_version_limit(
    tmp_path: Path,
) -> None:
    registry = InstalledDlcRegistry(tmp_path / "runtime" / "dlcs")
    publisher_key_id = "a" * 64
    for index in range(MAX_INSTALLED_VERSIONS_PER_DLC):
        registry.record_installed_package(
            "acme.versioned",
            InstalledDlcVersion(
                package_digest=f"{index:064x}",
                package_version=f"1.0.{index}",
                trust_status="trusted_signed",
                publisher_key_id=publisher_key_id,
            ),
        )

    with pytest.raises(DlcError) as exc_info:
        registry.record_installed_package(
            "acme.versioned",
            InstalledDlcVersion(
                package_digest=f"{MAX_INSTALLED_VERSIONS_PER_DLC:064x}",
                package_version="2.0.0",
                trust_status="trusted_signed",
                publisher_key_id=publisher_key_id,
            ),
        )

    assert exc_info.value.code == DlcErrorCode.DLC_VERSION_LIMIT_REACHED
    record = registry.get_installed_dlc("acme.versioned")
    assert record is not None
    assert len(record.installed_versions) == MAX_INSTALLED_VERSIONS_PER_DLC
