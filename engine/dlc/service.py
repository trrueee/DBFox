"""High-level DLC package service orchestrating verification, atomic installation, and registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.manifest import DlcManifest
from engine.dlc.registry import (
    InstalledDlcRecord,
    InstalledDlcRegistry,
    InstalledDlcVersion,
)
from engine.dlc.store import DlcPackageStore
from engine.dlc.trust import DlcTrustStatus, DlcTrustStore
from engine.dlc.verifier import DlcPackageVerifier, VerifiedDlcPackage


_DLC_LIFECYCLE_MUTATION_LOCK = RLock()


@dataclass(frozen=True)
class DlcInstallationResult:
    """Result of a successful, code-free DLC package installation."""

    dlc_id: str
    version: str
    package_digest: str
    install_dir: Path
    trust_status: DlcTrustStatus
    publisher_key_id: str | None


@dataclass(frozen=True)
class DlcUninstallResult:
    """Result of removing registry ownership and unreferenced executable bytes."""

    dlc_id: str
    package_digest: str
    package_digests: tuple[str, ...]
    executable_bytes_removed: bool
    data_retained: bool = True


@dataclass(frozen=True)
class DlcVersionRemovalResult:
    """Result of explicitly removing one inactive, unselected package version."""

    dlc_id: str
    package_digest: str
    executable_bytes_removed: bool


class DlcPackageService:
    """Orchestrates package verification, storage, and registry operations without code execution."""

    def __init__(
        self,
        storage_root: Path,
        trust_store: DlcTrustStore | None = None,
    ) -> None:
        self.storage_root = storage_root.resolve()
        self.trust_store = trust_store or DlcTrustStore(storage_root=self.storage_root)
        self.verifier = DlcPackageVerifier(self.trust_store)
        self.store = DlcPackageStore(self.storage_root)
        self.registry = InstalledDlcRegistry(self.storage_root)

    def inspect_from_file(self, archive_path: Path) -> VerifiedDlcPackage:
        """Authenticate a v2 single-file package without installing or trusting it."""
        return self.verifier.authenticate_archive_file(archive_path)

    def trust_publisher_from_file(
        self,
        archive_path: Path,
        *,
        expected_package_digest: str,
        expected_publisher_key_id: str,
    ) -> str:
        """Re-authenticate an inspected v2 package before persisting its actual key."""
        with _DLC_LIFECYCLE_MUTATION_LOCK:
            return self._trust_publisher_from_file(
                archive_path,
                expected_package_digest=expected_package_digest,
                expected_publisher_key_id=expected_publisher_key_id,
            )

    def _trust_publisher_from_file(
        self,
        archive_path: Path,
        *,
        expected_package_digest: str,
        expected_publisher_key_id: str,
    ) -> str:
        verified_package = self.verifier.authenticate_archive_file(archive_path)
        if verified_package.manifest.manifest_schema_version != 2:
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                "Publisher trust prompts are supported only for single-file manifest schema v2 packages",
            )
        if verified_package.package_digest != expected_package_digest.lower():
            raise DlcError(
                DlcErrorCode.PACKAGE_TAMPERED,
                "Package digest changed after inspection; publisher trust was not persisted",
                details={
                    "expected_package_digest": expected_package_digest.lower(),
                    "actual_package_digest": verified_package.package_digest,
                },
            )
        if verified_package.publisher_key_id != expected_publisher_key_id.lower():
            raise DlcError(
                DlcErrorCode.PUBLISHER_KEY_MISMATCH,
                "Embedded publisherKey changed after inspection; publisher trust was not persisted",
                details={
                    "expected_publisher_key_id": expected_publisher_key_id.lower(),
                    "actual_publisher_key_id": verified_package.publisher_key_id,
                },
            )
        publisher_key_base64 = verified_package.publisher_key_base64
        if publisher_key_base64 is None:
            raise DlcError(
                DlcErrorCode.INVALID_SIGNATURE,
                "Authenticated v2 package did not yield an embedded publisher key",
            )
        return self.trust_store.add_trusted_key(publisher_key_base64)

    def install_from_file(
        self,
        archive_path: Path,
        *,
        developer_mode: bool = False,
        publisher_key_base64: str | None = None,
    ) -> DlcInstallationResult:
        """Atomically verify and install a package without executing extension code."""
        with _DLC_LIFECYCLE_MUTATION_LOCK:
            return self._install_from_file(
                archive_path,
                developer_mode=developer_mode,
                publisher_key_base64=publisher_key_base64,
            )

    def _install_from_file(
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

        existing = self.registry.get_installed_dlc(verified_pkg.manifest.id)
        if existing is not None:
            installed = existing.package_for_digest(verified_pkg.package_digest)
            if installed is not None:
                return DlcInstallationResult(
                    dlc_id=existing.dlc_id,
                    version=installed.package_version,
                    package_digest=installed.package_digest,
                    install_dir=self.store.get_package_dir(installed.package_digest),
                    trust_status=DlcTrustStatus(installed.trust_status),
                    publisher_key_id=installed.publisher_key_id,
                )

        # 2. Extract and store package in immutable content-addressed store
        was_stored = self.store.is_package_stored(verified_pkg.package_digest)
        install_dir = self.store.stage_and_install_package(verified_pkg)

        # 3. Create and commit installed registry record
        package = InstalledDlcVersion(
            package_digest=verified_pkg.package_digest,
            package_version=verified_pkg.manifest.version,
            trust_status=verified_pkg.trust_status.value,
            publisher_key_id=verified_pkg.publisher_key_id,
        )
        try:
            self.registry.record_installed_package(verified_pkg.manifest.id, package)
        except Exception:
            if not was_stored:
                try:
                    self.store.remove_package(verified_pkg.package_digest)
                except DlcError:
                    pass
            raise

        return DlcInstallationResult(
            dlc_id=verified_pkg.manifest.id,
            version=verified_pkg.manifest.version,
            package_digest=verified_pkg.package_digest,
            install_dir=install_dir,
            trust_status=verified_pkg.trust_status,
            publisher_key_id=verified_pkg.publisher_key_id,
        )

    def set_desired_enabled(self, dlc_id: str, enabled: bool) -> InstalledDlcRecord:
        """Update only persistent desired state; active runtime truth is unchanged."""
        with _DLC_LIFECYCLE_MUTATION_LOCK:
            if self.registry.get_installed_dlc(dlc_id) is None:
                raise DlcError(
                    DlcErrorCode.DLC_NOT_INSTALLED,
                    f"DLC '{dlc_id}' is not installed",
                )
            return self.registry.set_desired_enabled(dlc_id, enabled)

    def select_package(self, dlc_id: str, package_digest: str) -> InstalledDlcRecord:
        """Select an installed digest; activation remains restart-bound."""
        with _DLC_LIFECYCLE_MUTATION_LOCK:
            return self.registry.select_package(dlc_id, package_digest)

    def load_installed_manifest(self, record: InstalledDlcRecord) -> DlcManifest:
        """Load the signed manifest copy from the selected immutable package."""
        package_dir = self.store.get_package_dir(record.selected_digest).resolve()
        manifest_path = (package_dir / "manifest.json").resolve()
        if manifest_path.parent != package_dir or not manifest_path.is_file():
            raise DlcError(
                DlcErrorCode.PACKAGE_MISSING,
                f"Installed package manifest is missing for DLC '{record.dlc_id}'",
            )
        manifest = DlcManifest.from_bytes(manifest_path.read_bytes())
        if manifest.id != record.dlc_id or manifest.version != record.package_version:
            raise DlcError(
                DlcErrorCode.PACKAGE_TAMPERED,
                f"Installed manifest identity does not match registry for DLC '{record.dlc_id}'",
            )
        return manifest

    def entrypoint_is_present(
        self,
        record: InstalledDlcRecord,
        entrypoint: str | None,
    ) -> bool:
        """Check one manifest entrypoint without permitting path escape."""
        if entrypoint is None:
            return False
        package_dir = self.store.get_package_dir(record.selected_digest).resolve()
        candidate = (package_dir / entrypoint).resolve()
        return candidate.is_relative_to(package_dir) and candidate.is_file()

    def uninstall(
        self,
        dlc_id: str,
        *,
        active_package_digests: set[str] | frozenset[str],
    ) -> DlcUninstallResult:
        """Remove one inactive, disabled DLC while retaining its owned data directory."""
        with _DLC_LIFECYCLE_MUTATION_LOCK:
            return self._uninstall(
                dlc_id,
                active_package_digests=active_package_digests,
            )

    def remove_version(
        self,
        dlc_id: str,
        package_digest: str,
        *,
        active_package_digests: set[str] | frozenset[str],
    ) -> DlcVersionRemovalResult:
        """Remove one explicit old version without touching other installed versions."""
        with _DLC_LIFECYCLE_MUTATION_LOCK:
            record = self.registry.get_installed_dlc(dlc_id)
            if record is None:
                raise DlcError(
                    DlcErrorCode.DLC_NOT_INSTALLED,
                    f"DLC '{dlc_id}' is not installed",
                )
            if package_digest in active_package_digests:
                raise DlcError(
                    DlcErrorCode.DLC_VERSION_ACTIVE,
                    f"Active package bytes for DLC '{dlc_id}' cannot be removed",
                )
            removed = self.registry.remove_installed_version(dlc_id, package_digest)
            remaining_digests = {
                version.package_digest
                for item in self.registry.list_installed_dlcs()
                for version in item.installed_versions
            }
            executable_bytes_removed = False
            if removed.package_digest not in remaining_digests:
                executable_bytes_removed = self.store.remove_package(
                    removed.package_digest
                )
            return DlcVersionRemovalResult(
                dlc_id=dlc_id,
                package_digest=removed.package_digest,
                executable_bytes_removed=executable_bytes_removed,
            )

    def _uninstall(
        self,
        dlc_id: str,
        *,
        active_package_digests: set[str] | frozenset[str],
    ) -> DlcUninstallResult:
        record = self.registry.get_installed_dlc(dlc_id)
        if record is None:
            raise DlcError(
                DlcErrorCode.DLC_NOT_INSTALLED,
                f"DLC '{dlc_id}' is not installed",
            )
        if record.desired_enabled:
            raise DlcError(
                DlcErrorCode.DLC_DISABLE_REQUIRED,
                f"DLC '{dlc_id}' must be disabled before uninstall",
            )
        installed_digests = {
            item.package_digest for item in record.installed_versions
        }
        if installed_digests & active_package_digests:
            raise DlcError(
                DlcErrorCode.DLC_ACTIVE,
                f"Active package bytes for DLC '{dlc_id}' cannot be removed",
            )

        removed = self.registry.remove_installed_dlc(dlc_id)
        remaining_digests = {
            version.package_digest
            for item in self.registry.list_installed_dlcs()
            for version in item.installed_versions
        }
        removed_digests = tuple(
            item.package_digest for item in removed.installed_versions
        )
        removal_results = [
            self.store.remove_package(package_digest)
            for package_digest in removed_digests
            if package_digest not in remaining_digests
        ]
        return DlcUninstallResult(
            dlc_id=removed.dlc_id,
            package_digest=removed.selected_digest,
            package_digests=removed_digests,
            executable_bytes_removed=bool(removal_results) and all(removal_results),
        )
