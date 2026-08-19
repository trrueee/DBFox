"""High-level DLC package service orchestrating verification, atomic installation, and registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.dlc.registry import InstalledDlcRecord, InstalledDlcRegistry
from engine.dlc.store import DlcPackageStore
from engine.dlc.trust import DlcTrustStatus, DlcTrustStore
from engine.dlc.verifier import DlcPackageVerifier



@dataclass(frozen=True)
class DlcInstallationResult:
    """Result of a successful, code-free DLC package installation."""

    dlc_id: str
    version: str
    package_digest: str
    install_dir: Path
    trust_status: DlcTrustStatus
    publisher_key_id: str | None


class DlcPackageService:
    """Orchestrates package verification, storage, and registry operations without code execution."""

    def __init__(
        self,
        storage_root: Path,
        trust_store: DlcTrustStore | None = None,
    ) -> None:
        self.storage_root = storage_root.resolve()
        self.trust_store = trust_store or DlcTrustStore()
        self.verifier = DlcPackageVerifier(self.trust_store)
        self.store = DlcPackageStore(self.storage_root)
        self.registry = InstalledDlcRegistry(self.storage_root)

    def install_from_file(
        self,
        archive_path: Path,
        *,
        developer_mode: bool = False,
        publisher_key_base64: str | None = None,
    ) -> DlcInstallationResult:
        """Atomically install a .dbfox-dlc package from an archive file.

        Guarantees:
        1. Package is parsed and bounded without executing any Python/JS code.
        2. Extracted files are safely staged and atomically renamed to content-addressed directory.
        3. Registry is updated atomically.
        4. If verification or staging fails, no half-installed registry entries or orphaned state remain.
        """
        # 1. Verify archive format, integrity, compatibility, and cryptographic signature
        verified_pkg = self.verifier.verify_archive_file(
            archive_path,
            developer_mode=developer_mode,
            publisher_key_base64=publisher_key_base64,
        )

        # 2. Extract and store package in immutable content-addressed store
        install_dir = self.store.stage_and_install_package(verified_pkg)

        # 3. Create and commit installed registry record
        record = InstalledDlcRecord(
            dlc_id=verified_pkg.manifest.id,
            selected_digest=verified_pkg.package_digest,
            package_version=verified_pkg.manifest.version,
            desired_enabled=False,
            runtime_state="installed_disabled",
            trust_status=verified_pkg.trust_status.value,
            publisher_key_id=verified_pkg.publisher_key_id,
        )
        self.registry.record_installed_dlc(record)

        return DlcInstallationResult(
            dlc_id=verified_pkg.manifest.id,
            version=verified_pkg.manifest.version,
            package_digest=verified_pkg.package_digest,
            install_dir=install_dir,
            trust_status=verified_pkg.trust_status,
            publisher_key_id=verified_pkg.publisher_key_id,
        )
