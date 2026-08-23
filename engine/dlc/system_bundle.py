"""Bootstrap official capability DLCs through the verified package lifecycle.

The bundle manifest is generated during the Frozen Sidecar build and embedded
inside that executable. Electron Resources carries only package bytes. This
keeps the publisher key and exact package digests on the Sidecar integrity root.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.dlc.service import DlcPackageService
from engine.dlc.trust import (
    DlcTrustStatus,
    DlcTrustStore,
    compute_key_fingerprint,
    public_key_from_base64,
)

SYSTEM_DLC_BUNDLE_FILENAME = "_system_dlc_bundle.json"
MAX_SYSTEM_DLC_BUNDLE_BYTES = 64 * 1024
MAX_SYSTEM_DLC_PACKAGES = 16


class SystemDlcPackagePin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    version: str = Field(min_length=1, max_length=64)
    filename: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*\.dbfox-dlc$")
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    default_enabled: bool = True

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if Path(value).name != value:
            raise ValueError("system DLC filename must be a single path component")
        return value


class SystemDlcBundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    publisher_public_key: str = Field(min_length=44, max_length=44)
    packages: tuple[SystemDlcPackagePin, ...] = Field(
        min_length=1,
        max_length=MAX_SYSTEM_DLC_PACKAGES,
    )

    @field_validator("publisher_public_key")
    @classmethod
    def validate_publisher_key(cls, value: str) -> str:
        public_key_from_base64(value)
        return value

    @model_validator(mode="after")
    def validate_unique_packages(self) -> "SystemDlcBundleManifest":
        ids = [item.dlc_id for item in self.packages]
        filenames = [item.filename for item in self.packages]
        if len(ids) != len(set(ids)):
            raise ValueError("system DLC ids must be unique")
        if len(filenames) != len(set(filenames)):
            raise ValueError("system DLC filenames must be unique")
        return self


@dataclass(frozen=True, slots=True)
class SystemDlcBootstrapResult:
    dlc_ids: tuple[str, ...]
    publisher_key_id: str


def embedded_system_dlc_manifest_path() -> Path:
    return Path(__file__).resolve().with_name(SYSTEM_DLC_BUNDLE_FILENAME)


def load_system_dlc_bundle_manifest(path: Path) -> SystemDlcBundleManifest:
    try:
        resolved = path.resolve(strict=True)
        size = resolved.stat().st_size
    except OSError as exc:
        raise RuntimeError("System DLC bundle manifest is unavailable") from exc
    if not resolved.is_file() or size > MAX_SYSTEM_DLC_BUNDLE_BYTES:
        raise RuntimeError(
            "System DLC bundle manifest is unavailable or exceeds its size limit"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return SystemDlcBundleManifest.model_validate(payload)
    except Exception as exc:
        raise RuntimeError(f"System DLC bundle manifest is invalid: {exc}") from exc


def bootstrap_system_dlcs(
    storage_root: Path,
    package_root: Path,
    *,
    manifest_path: Path | None = None,
) -> SystemDlcBootstrapResult:
    """Install and select the exact official packages embedded in this build.

    A first install defaults to enabled. Existing ``desired_enabled`` state is
    preserved so a user's explicit disable survives restarts and app upgrades.
    """

    manifest = load_system_dlc_bundle_manifest(
        manifest_path or embedded_system_dlc_manifest_path()
    )
    try:
        resolved_packages = package_root.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("System DLC package root is unavailable") from exc
    if not resolved_packages.is_dir():
        raise RuntimeError("System DLC package root is not a directory")

    trust_store = DlcTrustStore(
        trusted_keys={"dbfox.system": manifest.publisher_public_key},
        storage_root=storage_root,
    )
    publisher_key_id = compute_key_fingerprint(
        public_key_from_base64(manifest.publisher_public_key)
    )
    service = DlcPackageService(storage_root, trust_store=trust_store)

    installed_ids: list[str] = []
    for pin in manifest.packages:
        try:
            archive = (resolved_packages / pin.filename).resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(
                f"System DLC package is unavailable: {pin.filename}"
            ) from exc
        if (
            archive.parent != resolved_packages
            or not archive.is_file()
            or archive.is_symlink()
        ):
            raise RuntimeError(f"System DLC package path is invalid: {pin.filename}")
        if _sha256(archive) != pin.package_digest:
            raise RuntimeError(
                f"System DLC package digest mismatch for {pin.dlc_id}"
            )

        existing = service.registry.get_installed_dlc(pin.dlc_id)
        result = service.install_from_file(archive)
        if (
            result.dlc_id != pin.dlc_id
            or result.version != pin.version
            or result.package_digest != pin.package_digest
            or result.publisher_key_id != publisher_key_id
            or result.trust_status is not DlcTrustStatus.TRUSTED_SIGNED
        ):
            raise RuntimeError(
                f"System DLC package identity mismatch for {pin.dlc_id}"
            )

        service.select_package(pin.dlc_id, pin.package_digest)
        if existing is None:
            service.set_desired_enabled(pin.dlc_id, pin.default_enabled)
        installed_ids.append(pin.dlc_id)

    return SystemDlcBootstrapResult(
        dlc_ids=tuple(installed_ids),
        publisher_key_id=publisher_key_id,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "SYSTEM_DLC_BUNDLE_FILENAME",
    "SystemDlcBootstrapResult",
    "SystemDlcBundleManifest",
    "SystemDlcPackagePin",
    "bootstrap_system_dlcs",
    "embedded_system_dlc_manifest_path",
    "load_system_dlc_bundle_manifest",
]
