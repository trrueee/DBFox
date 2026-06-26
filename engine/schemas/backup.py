from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.schemas import _to_iso


class BackupCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    datasource_id: str = Field(min_length=1, max_length=128)
    label: str | None = Field(default=None, max_length=128)
    allow_fallback: bool = True


class RestoreConfirmRequest(BaseModel):
    """Confirmation payload for backup restore (body, not query string)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    confirm_token: str | None = Field(default=None, min_length=1, max_length=256)
    confirm_text: str | None = Field(default=None, min_length=1, max_length=256)
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
