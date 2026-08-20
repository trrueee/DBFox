"""Content-addressed package storage and atomic installation extraction for DBFox DLCs."""

from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.verifier import VerifiedDlcPackage

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DlcPackageStore:
    """Manages the immutable content-addressed storage for installed DLC packages."""

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root.resolve()
        self.packages_dir = self.storage_root / "packages"
        self.staging_dir = self.storage_root / "staging"
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def get_package_dir(self, package_digest: str) -> Path:
        """Return the content-addressed directory path for a package digest."""
        if not _SHA256_PATTERN.fullmatch(package_digest):
            raise DlcError(
                DlcErrorCode.INVALID_INTEGRITY,
                "Package digest must be a lowercase SHA-256 hex value",
            )
        return self.packages_dir / f"sha256-{package_digest}"

    def is_package_stored(self, package_digest: str) -> bool:
        """Check if package directory exists and is non-empty."""
        pkg_dir = self.get_package_dir(package_digest)
        return pkg_dir.is_dir() and (pkg_dir / "manifest.json").is_file()

    def stage_and_install_package(self, verified_pkg: VerifiedDlcPackage) -> Path:
        """Atomically extract and install verified package bytes into content-addressed store.

        Returns final installed package directory Path.
        """
        final_dir = self.get_package_dir(verified_pkg.package_digest)

        # If already safely stored, return existing directory
        if self.is_package_stored(verified_pkg.package_digest):
            return final_dir

        # 1. Create temporary staging directory on the same filesystem
        staging_pkg_dir = Path(tempfile.mkdtemp(prefix="dlc_stage_", dir=str(self.staging_dir)))

        try:
            # 2. Extract verified ZIP entries into staging directory
            with zipfile.ZipFile(io.BytesIO(verified_pkg.raw_archive_bytes), mode="r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    # Normalize target path
                    rel_path = info.filename.replace("\\", "/").strip("/")
                    target_file = (staging_pkg_dir / rel_path).resolve()

                    # Enforce strict path containment
                    if not target_file.is_relative_to(staging_pkg_dir.resolve()):
                        raise DlcError(
                            DlcErrorCode.UNSAFE_PATH,
                            f"Extraction path escaped staging root: '{info.filename}'",
                        )

                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # 3. Atomically move/rename staging directory to final content-addressed directory
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)

            try:
                os.replace(staging_pkg_dir, final_dir)
            except OSError:
                # Fallback if atomic replace fails across subvolumes
                if not final_dir.exists():
                    shutil.move(str(staging_pkg_dir), str(final_dir))

            return final_dir

        except Exception as exc:
            # Clean up staging directory on any failure
            shutil.rmtree(staging_pkg_dir, ignore_errors=True)
            if isinstance(exc, DlcError):
                raise
            raise DlcError(
                DlcErrorCode.INSTALL_IO_ERROR,
                f"Failed to extract package into content-addressed store: {exc}",
            ) from exc

    def remove_package(self, package_digest: str) -> bool:
        """Remove one exact content-addressed package directory, if present."""
        package_dir = self.get_package_dir(package_digest).resolve()
        packages_root = self.packages_dir.resolve()
        if package_dir.parent != packages_root:
            raise DlcError(
                DlcErrorCode.UNSAFE_PATH,
                "Package removal target escaped the content-addressed store",
            )
        if not package_dir.exists():
            return False
        if not package_dir.is_dir():
            raise DlcError(
                DlcErrorCode.INSTALL_IO_ERROR,
                "Package removal target is not a directory",
            )
        try:
            shutil.rmtree(package_dir)
        except OSError as exc:
            raise DlcError(
                DlcErrorCode.INSTALL_IO_ERROR,
                "Failed to remove unreferenced package bytes",
            ) from exc
        return True
