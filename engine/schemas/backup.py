from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.schemas import _to_iso


class BackupCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    datasource_id: str = Field(min_length=1, max_length=128)
    label: str | None = Field(default=None, max_length=128)


class BackupRestoreRequest(BaseModel):
    """Explicit generation-fenced request for isolated restore and cutover."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    expected_datasource_generation: int = Field(ge=1)
    confirmation: Literal["restore-to-isolated-database"]


class RestoreOperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    backup_id: str
    datasource_id: str
    status: str
    source_database_name: str
    target_database_name: str
    expected_generation: int
    committed_generation: int | None = None
    validated_table_count: int | None = None
    error_code: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @field_validator("started_at", "completed_at", mode="before")
    @classmethod
    def _iso_restore_dates(cls, v: Any) -> str | None:
        return _to_iso(v)


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
    source_connection_generation: int | None = None
    source_profile_fingerprint: str | None = None
    source_database_name: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    created_at: str | None = None

    @field_validator("started_at", "completed_at", "created_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)
