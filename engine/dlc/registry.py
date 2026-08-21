"""Machine-level Installed DLC Registry and lifecycle state tracking."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.integrity import canonical_json_bytes

REGISTRY_SCHEMA_VERSION = 2
MAX_REGISTRY_BYTES = 5 * 1024 * 1024  # 5 MiB
MAX_INSTALLED_VERSIONS_PER_DLC = 32


class InstalledDlcVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_version: str
    trust_status: str
    publisher_key_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    installed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InstalledDlcRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    installed_versions: tuple[InstalledDlcVersion, ...] = Field(
        min_length=1,
        max_length=MAX_INSTALLED_VERSIONS_PER_DLC,
    )
    selected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    desired_enabled: bool = False
    last_failure_code: str | None = None

    @model_validator(mode="after")
    def validate_version_set(self) -> "InstalledDlcRecord":
        digests = [item.package_digest for item in self.installed_versions]
        versions = [item.package_version for item in self.installed_versions]
        if len(digests) != len(set(digests)):
            raise ValueError("installed DLC package digests must be unique")
        if len(versions) != len(set(versions)):
            raise ValueError("installed DLC package versions must be unique")
        if self.selected_digest not in digests:
            raise ValueError("selected_digest must reference an installed package")
        return self

    def package_for_digest(self, package_digest: str) -> InstalledDlcVersion | None:
        return next(
            (
                item
                for item in self.installed_versions
                if item.package_digest == package_digest
            ),
            None,
        )

    @property
    def selected_package(self) -> InstalledDlcVersion:
        package = self.package_for_digest(self.selected_digest)
        if package is None:  # pragma: no cover - enforced by model validation
            raise ValueError("selected package is missing")
        return package

    @property
    def package_version(self) -> str:
        return self.selected_package.package_version

    @property
    def trust_status(self) -> str:
        return self.selected_package.trust_status

    @property
    def publisher_key_id(self) -> str | None:
        return self.selected_package.publisher_key_id

    @property
    def installed_at(self) -> str:
        return self.selected_package.installed_at


class _LegacyInstalledDlcRecord(BaseModel):
    """Strict one-release migration reader for registry schema v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    selected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_version: str
    desired_enabled: bool = False
    runtime_state: str = "installed_disabled"
    trust_status: str
    publisher_key_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    installed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_failure_code: str | None = None


class _LegacyRegistryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1, le=1)
    installed_dlcs: dict[str, _LegacyInstalledDlcRecord] = Field(default_factory=dict)


class RegistryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=REGISTRY_SCHEMA_VERSION, ge=2, le=2)
    installed_dlcs: dict[str, InstalledDlcRecord] = Field(default_factory=dict)


class InstalledDlcRegistry:
    """Manages the persistent installed DLC registry (registry.json)."""

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root.resolve()
        self.registry_file = self.storage_root / "registry.json"

    def load(self) -> dict[str, InstalledDlcRecord]:
        """Load installed DLC records from registry.json.

        Returns empty dict if file does not exist.
        Raises DlcError(DlcErrorCode.REGISTRY_CORRUPT) on corrupt file.
        """
        if not self.registry_file.is_file():
            return {}

        file_size = self.registry_file.stat().st_size
        if file_size > MAX_REGISTRY_BYTES:
            raise DlcError(
                DlcErrorCode.REGISTRY_CORRUPT,
                f"registry.json exceeds size limit ({file_size} bytes)",
            )

        try:
            raw_bytes = self.registry_file.read_bytes()
            data = json.loads(raw_bytes.decode("utf-8"))
            schema_version = data.get("schema_version") if isinstance(data, dict) else None
            if schema_version == 1:
                legacy = _LegacyRegistryPayload.model_validate(data)
                return {
                    dlc_id: InstalledDlcRecord(
                        dlc_id=record.dlc_id,
                        installed_versions=(
                            InstalledDlcVersion(
                                package_digest=record.selected_digest,
                                package_version=record.package_version,
                                trust_status=record.trust_status,
                                publisher_key_id=record.publisher_key_id,
                                installed_at=record.installed_at,
                            ),
                        ),
                        selected_digest=record.selected_digest,
                        desired_enabled=record.desired_enabled,
                        last_failure_code=record.last_failure_code,
                    )
                    for dlc_id, record in legacy.installed_dlcs.items()
                }
            payload = RegistryPayload.model_validate(data)
            return dict(payload.installed_dlcs)
        except Exception as exc:
            raise DlcError(
                DlcErrorCode.REGISTRY_CORRUPT,
                f"Failed to parse registry.json: {exc}",
            ) from exc

    def save(self, records: dict[str, InstalledDlcRecord]) -> None:
        """Atomically save installed DLC records to registry.json."""
        payload = RegistryPayload(
            schema_version=REGISTRY_SCHEMA_VERSION,
            installed_dlcs=records,
        )
        canonical_bytes = canonical_json_bytes(payload.model_dump(exclude_none=True))

        # Write to temporary file in same directory for atomic replace
        self.storage_root.mkdir(parents=True, exist_ok=True)
        fd, temp_path_str = tempfile.mkstemp(
            prefix="registry_tmp_",
            dir=str(self.storage_root),
        )
        temp_path = Path(temp_path_str)

        try:
            with os.fdopen(fd, "wb") as f:
                f.write(canonical_bytes)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path, self.registry_file)
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise DlcError(
                DlcErrorCode.INSTALL_IO_ERROR,
                f"Failed to atomically write registry.json: {exc}",
            ) from exc

    def record_installed_package(
        self,
        dlc_id: str,
        package: InstalledDlcVersion,
    ) -> InstalledDlcRecord:
        """Add one immutable version without changing an existing selection."""
        current = self.load()
        existing = current.get(dlc_id)

        if existing is not None:
            if existing.package_for_digest(package.package_digest) is not None:
                return existing
            if any(
                item.package_version == package.package_version
                for item in existing.installed_versions
            ):
                raise DlcError(
                    DlcErrorCode.CONFLICTING_DIGEST,
                    f"DLC '{dlc_id}' version '{package.package_version}' is already installed with a different digest",
                )
            if any(
                item.publisher_key_id != package.publisher_key_id
                for item in existing.installed_versions
            ):
                raise DlcError(
                    DlcErrorCode.PUBLISHER_KEY_MISMATCH,
                    f"DLC '{dlc_id}' package publisher does not match its installed versions",
                )
            if len(existing.installed_versions) >= MAX_INSTALLED_VERSIONS_PER_DLC:
                raise DlcError(
                    DlcErrorCode.DLC_VERSION_LIMIT_REACHED,
                    f"DLC '{dlc_id}' reached the installed-version limit",
                )
            record = existing.model_copy(
                update={"installed_versions": (*existing.installed_versions, package)}
            )
        else:
            record = InstalledDlcRecord(
                dlc_id=dlc_id,
                installed_versions=(package,),
                selected_digest=package.package_digest,
            )

        current[dlc_id] = record
        self.save(current)
        return record

    def get_installed_dlc(self, dlc_id: str) -> InstalledDlcRecord | None:
        """Retrieve record for a specific dlc_id."""
        return self.load().get(dlc_id)

    def list_installed_dlcs(self) -> list[InstalledDlcRecord]:
        """List all installed DLC records."""
        return list(self.load().values())

    def set_desired_enabled(self, dlc_id: str, enabled: bool) -> InstalledDlcRecord:
        """Update desired_enabled state for an installed DLC."""
        current = self.load()
        existing = current.get(dlc_id)
        if not existing:
            raise DlcError(
                DlcErrorCode.MISSING_FILE,
                f"Cannot update state: DLC '{dlc_id}' is not installed",
            )

        updated = existing.model_copy(
            update={"desired_enabled": enabled}
        )
        current[dlc_id] = updated
        self.save(current)
        return updated

    def select_package(self, dlc_id: str, package_digest: str) -> InstalledDlcRecord:
        """Select one installed digest without changing desired enabled state."""
        current = self.load()
        existing = current.get(dlc_id)
        if existing is None:
            raise DlcError(
                DlcErrorCode.DLC_NOT_INSTALLED,
                f"DLC '{dlc_id}' is not installed",
            )
        if existing.package_for_digest(package_digest) is None:
            raise DlcError(
                DlcErrorCode.DLC_VERSION_NOT_INSTALLED,
                f"DLC '{dlc_id}' does not have package '{package_digest}' installed",
            )
        if existing.selected_digest == package_digest:
            return existing
        updated = existing.model_copy(update={"selected_digest": package_digest})
        current[dlc_id] = updated
        self.save(current)
        return updated

    def remove_installed_version(
        self,
        dlc_id: str,
        package_digest: str,
    ) -> InstalledDlcVersion:
        """Remove one unselected version reference from the registry."""
        current = self.load()
        existing = current.get(dlc_id)
        if existing is None:
            raise DlcError(
                DlcErrorCode.DLC_NOT_INSTALLED,
                f"DLC '{dlc_id}' is not installed",
            )
        package = existing.package_for_digest(package_digest)
        if package is None:
            raise DlcError(
                DlcErrorCode.DLC_VERSION_NOT_INSTALLED,
                f"DLC '{dlc_id}' does not have package '{package_digest}' installed",
            )
        if existing.selected_digest == package_digest:
            raise DlcError(
                DlcErrorCode.DLC_VERSION_SELECTED,
                f"Selected package bytes for DLC '{dlc_id}' cannot be removed",
            )
        updated = existing.model_copy(
            update={
                "installed_versions": tuple(
                    item
                    for item in existing.installed_versions
                    if item.package_digest != package_digest
                )
            }
        )
        current[dlc_id] = updated
        self.save(current)
        return package

    def remove_installed_dlc(self, dlc_id: str) -> InstalledDlcRecord:
        """Atomically remove one installed record and return its previous value."""
        current = self.load()
        existing = current.pop(dlc_id, None)
        if existing is None:
            raise DlcError(
                DlcErrorCode.DLC_NOT_INSTALLED,
                f"DLC '{dlc_id}' is not installed",
            )
        self.save(current)
        return existing
