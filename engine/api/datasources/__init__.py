from __future__ import annotations

from fastapi import APIRouter

from engine.api.datasources import crud, health, metadata, schema
from engine.api.datasources.common import datasource_to_dict as _datasource_to_dict
from engine.api.datasources.metadata import ColumnMetadataUpdateRequest, TableMetadataUpdateRequest
from engine.api.datasources.schema import SchemaSyncRequest, _sync_catalog

router = APIRouter()
router.include_router(crud.router)
router.include_router(health.router)
router.include_router(schema.router)
router.include_router(metadata.router)

__all__ = [
    "ColumnMetadataUpdateRequest",
    "SchemaSyncRequest",
    "TableMetadataUpdateRequest",
    "_datasource_to_dict",
    "_sync_catalog",
    "router",
]
