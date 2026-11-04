from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.schemas import _to_iso


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)
