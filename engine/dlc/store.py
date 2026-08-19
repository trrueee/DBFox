"""Content-addressed package storage and atomic installation extraction for DBFox DLCs."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.verifier import VerifiedDlcPackage


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
        norm_digest = package_digest.lower()
        return self.packages_dir / f"sha256-{norm_digest}"

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
                    if not str(target_file).startswith(str(staging_pkg_dir.resolve())):
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
