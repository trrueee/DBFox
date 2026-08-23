from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from engine.schemas import _to_iso


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    status: str | None = None
    datasource_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)
