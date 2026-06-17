from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _to_iso(v: Any) -> str | None:
    if v is None: return None
    if isinstance(v, datetime): return v.isoformat()
    return str(v)


class BackupCreateRequest(BaseModel):
    datasource_id: str
    label: str | None = None
    allow_fallback: bool = True


class BackupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    datasource_id: str | None = None
    environment_id: str | None = None
    label: str | None = None
    backup_type: str | None = None
    status: str | None = None
    file_path: str | None = None
    file_size_bytes: int | None = None
    checksum_sha256: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    created_at: str | None = None

    @field_validator("started_at", "completed_at", "created_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)
