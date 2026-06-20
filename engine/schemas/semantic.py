from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from engine.schemas import _to_iso


# NOTE: SemanticAlias* and SemanticMetric* / SemanticDimension* schemas were
# removed in the MVP simplification (2026-06-20).


class WorkspaceTableScopeUpdateRequest(BaseModel):
    project_id: str
    datasource_id: str
    enabled_table_ids: list[str]


class WorkspaceTableScopeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    data_source_id: str
    table_id: str
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)
