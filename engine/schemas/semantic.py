from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _to_iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


class SemanticAliasCreateRequest(BaseModel):
    data_source_id: str
    alias: str
    target_type: str
    target: str
    description: str | None = None


class SemanticAliasUpdateRequest(BaseModel):
    alias: str | None = None
    target_type: str | None = None
    target: str | None = None
    description: str | None = None


class SemanticMetricCreateRequest(BaseModel):
    data_source_id: str
    name: str
    expression: str
    source_columns_json: str | None = None
    description: str | None = None


class SemanticMetricUpdateRequest(BaseModel):
    name: str | None = None
    expression: str | None = None
    source_columns_json: str | None = None
    description: str | None = None


class SemanticDimensionCreateRequest(BaseModel):
    data_source_id: str
    name: str
    column_ref: str
    transform: str | None = None
    description: str | None = None


class SemanticDimensionUpdateRequest(BaseModel):
    name: str | None = None
    column_ref: str | None = None
    transform: str | None = None
    description: str | None = None


class WorkspaceTableScopeUpdateRequest(BaseModel):
    project_id: str
    datasource_id: str
    enabled_table_ids: list[str]


# ── Response schemas ──

class SemanticAliasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    data_source_id: str
    alias: str
    target_type: str
    target: str
    description: str | None = None
    embedding_synced_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("embedding_synced_at", "created_at", "updated_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)


class SemanticMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    data_source_id: str
    name: str
    expression: str
    source_columns_json: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)


class SemanticDimensionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    data_source_id: str
    name: str
    column_ref: str
    transform: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _iso_dates(cls, v: Any) -> str | None:
        return _to_iso(v)


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
