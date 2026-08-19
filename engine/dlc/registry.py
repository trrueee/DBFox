"""Machine-level Installed DLC Registry and lifecycle state tracking."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


from engine.dlc.errors import DlcError, DlcErrorCode
from engine.dlc.integrity import canonical_json_bytes

REGISTRY_SCHEMA_VERSION = 1
MAX_REGISTRY_BYTES = 5 * 1024 * 1024  # 5 MiB


class InstalledDlcRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dlc_id: str
    selected_digest: str
    package_version: str
    desired_enabled: bool = False
    runtime_state: str = "installed_disabled"
    trust_status: str
    publisher_key_id: str | None = None
    installed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_failure_code: str | None = None


class RegistryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=REGISTRY_SCHEMA_VERSION, ge=1, le=1)
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

    def record_installed_dlc(self, record: InstalledDlcRecord) -> None:
        """Record or update an installed DLC in the registry."""
        current = self.load()
        existing = current.get(record.dlc_id)

        if existing:
            # Reject conflicting digest for same version
            if (
                existing.package_version == record.package_version
                and existing.selected_digest != record.selected_digest
            ):
                raise DlcError(
                    DlcErrorCode.CONFLICTING_DIGEST,
                    f"DLC '{record.dlc_id}' version '{record.package_version}' is already installed with a different digest: {existing.selected_digest}",
                )

        current[record.dlc_id] = record
        self.save(current)

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
            update={
                "desired_enabled": enabled,
                "runtime_state": "enable_pending_restart" if enabled else "disable_pending_restart",
            }
        )
        current[dlc_id] = updated
        self.save(current)
        return updated
