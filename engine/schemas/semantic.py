from __future__ import annotations

from pydantic import BaseModel


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
