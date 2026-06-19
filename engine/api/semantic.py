from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.models import (
    DataSource,
    Project,
    SchemaTable,
    SemanticAlias,
    SemanticDimension,
    SemanticMetric,
    WorkspaceTableScope,
)
from engine.schemas import (
    SemanticAliasCreateRequest,
    SemanticAliasUpdateRequest,
    SemanticDimensionCreateRequest,
    SemanticDimensionUpdateRequest,
    SemanticMetricCreateRequest,
    SemanticMetricUpdateRequest,
    WorkspaceTableScopeUpdateRequest,
)
from engine.schemas.semantic import (
    SemanticAliasResponse,
    SemanticMetricResponse,
    SemanticDimensionResponse,
    WorkspaceTableScopeResponse,
)

logger = logging.getLogger("dbfox.api.semantic")
router = APIRouter()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _alias_to_dict(a: SemanticAlias) -> dict[str, Any]:
    return SemanticAliasResponse.model_validate(a).model_dump(mode="json")


def _metric_to_dict(m: SemanticMetric) -> dict[str, Any]:
    return SemanticMetricResponse.model_validate(m).model_dump(mode="json")


def _dimension_to_dict(d: SemanticDimension) -> dict[str, Any]:
    return SemanticDimensionResponse.model_validate(d).model_dump(mode="json")


def _scope_to_dict(s: WorkspaceTableScope) -> dict[str, Any]:
    return WorkspaceTableScopeResponse.model_validate(s).model_dump(mode="json")


def _check_datasource(db: Session, datasource_id: str) -> DataSource:
    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail={"code": "DATASOURCE_NOT_FOUND", "message": f"Datasource {datasource_id} not found."})
    return ds


def _check_project(db: Session, project_id: str) -> Project:
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": f"Project {project_id} not found."})
    return proj


def _check_table_belongs(db: Session, table_id: str, datasource_id: str) -> SchemaTable:
    table = db.query(SchemaTable).filter(SchemaTable.id == table_id, SchemaTable.data_source_id == datasource_id).first()
    if not table:
        raise HTTPException(status_code=400, detail={"code": "TABLE_NOT_IN_DATASOURCE", "message": f"Table {table_id} does not belong to datasource {datasource_id}."})
    return table


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

@router.get("/semantic/aliases")
def api_list_aliases(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _check_datasource(db, datasource_id)
    items = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type != "sensitive"
        )
        .order_by(SemanticAlias.created_at.desc())
        .all()
    )
    return [_alias_to_dict(item) for item in items]


@router.post("/semantic/aliases")
def api_create_alias(req: SemanticAliasCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_datasource(db, req.data_source_id)
    existing = db.query(SemanticAlias).filter(
        SemanticAlias.data_source_id == req.data_source_id,
        SemanticAlias.alias == req.alias,
        SemanticAlias.target_type == req.target_type,
        SemanticAlias.target == req.target,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "ALIAS_EXISTS", "message": "This alias already exists."})
    item = SemanticAlias(
        id=str(uuid.uuid4()),
        data_source_id=req.data_source_id,
        alias=req.alias,
        target_type=req.target_type,
        target=req.target,
        description=req.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _alias_to_dict(item)


@router.put("/semantic/aliases/{id}")
def api_update_alias(id: str, req: SemanticAliasUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SemanticAlias).filter(SemanticAlias.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "ALIAS_NOT_FOUND", "message": f"Alias {id} not found."})
    alias_changed = False
    description_changed = False
    if req.alias is not None:
        if req.alias != item.alias:
            item.alias = req.alias  # type: ignore[assignment]
            alias_changed = True
    if req.target_type is not None:
        item.target_type = req.target_type  # type: ignore[assignment]
    if req.target is not None:
        item.target = req.target  # type: ignore[assignment]
    if req.description is not None:
        if req.description != item.description:
            item.description = req.description  # type: ignore[assignment]
            description_changed = True
    if alias_changed or description_changed:
        item.embedding_blob = None
        item.embedding_synced_at = None
    db.commit()
    db.refresh(item)
    return _alias_to_dict(item)


@router.delete("/semantic/aliases/{id}")
def api_delete_alias(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SemanticAlias).filter(SemanticAlias.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "ALIAS_NOT_FOUND", "message": f"Alias {id} not found."})
    db.delete(item)
    db.commit()
    return {"success": True, "message": "Alias deleted."}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/semantic/metrics")
def api_list_metrics(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _check_datasource(db, datasource_id)
    items = db.query(SemanticMetric).filter(SemanticMetric.data_source_id == datasource_id).order_by(SemanticMetric.created_at.desc()).all()
    return [_metric_to_dict(item) for item in items]


@router.post("/semantic/metrics")
def api_create_metric(req: SemanticMetricCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_datasource(db, req.data_source_id)
    existing = db.query(SemanticMetric).filter(
        SemanticMetric.data_source_id == req.data_source_id,
        SemanticMetric.name == req.name,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "METRIC_EXISTS", "message": "A metric with this name already exists."})
    item = SemanticMetric(
        id=str(uuid.uuid4()),
        data_source_id=req.data_source_id,
        name=req.name,
        expression=req.expression,
        source_columns_json=req.source_columns_json,
        description=req.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _metric_to_dict(item)


@router.put("/semantic/metrics/{id}")
def api_update_metric(id: str, req: SemanticMetricUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SemanticMetric).filter(SemanticMetric.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "METRIC_NOT_FOUND", "message": f"Metric {id} not found."})
    if req.name is not None:
        item.name = req.name  # type: ignore[assignment]
    if req.expression is not None:
        item.expression = req.expression  # type: ignore[assignment]
    if req.source_columns_json is not None:
        item.source_columns_json = req.source_columns_json  # type: ignore[assignment]
    if req.description is not None:
        item.description = req.description  # type: ignore[assignment]
    db.commit()
    db.refresh(item)
    return _metric_to_dict(item)


@router.delete("/semantic/metrics/{id}")
def api_delete_metric(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SemanticMetric).filter(SemanticMetric.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "METRIC_NOT_FOUND", "message": f"Metric {id} not found."})
    db.delete(item)
    db.commit()
    return {"success": True, "message": "Metric deleted."}


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

@router.get("/semantic/dimensions")
def api_list_dimensions(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _check_datasource(db, datasource_id)
    items = db.query(SemanticDimension).filter(SemanticDimension.data_source_id == datasource_id).order_by(SemanticDimension.created_at.desc()).all()
    return [_dimension_to_dict(item) for item in items]


@router.post("/semantic/dimensions")
def api_create_dimension(req: SemanticDimensionCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_datasource(db, req.data_source_id)
    existing = db.query(SemanticDimension).filter(
        SemanticDimension.data_source_id == req.data_source_id,
        SemanticDimension.name == req.name,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "DIMENSION_EXISTS", "message": "A dimension with this name already exists."})
    item = SemanticDimension(
        id=str(uuid.uuid4()),
        data_source_id=req.data_source_id,
        name=req.name,
        column_ref=req.column_ref,
        transform=req.transform,
        description=req.description,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _dimension_to_dict(item)


@router.put("/semantic/dimensions/{id}")
def api_update_dimension(id: str, req: SemanticDimensionUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SemanticDimension).filter(SemanticDimension.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "DIMENSION_NOT_FOUND", "message": f"Dimension {id} not found."})
    if req.name is not None:
        item.name = req.name  # type: ignore[assignment]
    if req.column_ref is not None:
        item.column_ref = req.column_ref  # type: ignore[assignment]
    if req.transform is not None:
        item.transform = req.transform  # type: ignore[assignment]
    if req.description is not None:
        item.description = req.description  # type: ignore[assignment]
    db.commit()
    db.refresh(item)
    return _dimension_to_dict(item)


@router.delete("/semantic/dimensions/{id}")
def api_delete_dimension(id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(SemanticDimension).filter(SemanticDimension.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail={"code": "DIMENSION_NOT_FOUND", "message": f"Dimension {id} not found."})
    db.delete(item)
    db.commit()
    return {"success": True, "message": "Dimension deleted."}


# ---------------------------------------------------------------------------
# Table Scope
# ---------------------------------------------------------------------------

@router.get("/semantic/table-scope")
def api_get_table_scope(
    project_id: str = Query(...),
    datasource_id: str = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    _check_project(db, project_id)
    _check_datasource(db, datasource_id)
    scopes = (
        db.query(WorkspaceTableScope)
        .filter(
            WorkspaceTableScope.project_id == project_id,
            WorkspaceTableScope.data_source_id == datasource_id,
        )
        .all()
    )
    return [_scope_to_dict(s) for s in scopes]


@router.post("/semantic/table-scope")
def api_update_table_scope(req: WorkspaceTableScopeUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_project(db, req.project_id)
    _check_datasource(db, req.datasource_id)

    for tid in req.enabled_table_ids:
        _check_table_belongs(db, tid, req.datasource_id)

    db.query(WorkspaceTableScope).filter(
        WorkspaceTableScope.project_id == req.project_id,
        WorkspaceTableScope.data_source_id == req.datasource_id,
    ).delete()

    for tid in req.enabled_table_ids:
        scope = WorkspaceTableScope(
            id=str(uuid.uuid4()),
            project_id=req.project_id,
            data_source_id=req.datasource_id,
            table_id=tid,
            enabled=True,
        )
        db.add(scope)

    db.commit()
    return {"success": True, "message": f"Table scope updated ({len(req.enabled_table_ids)} tables enabled)."}


from pydantic import BaseModel

class SyncEmbeddingsRequest(BaseModel):
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None


@router.post("/semantic/aliases/sync-embeddings")
def api_sync_embeddings(
    datasource_id: str = Query(...),
    req: SyncEmbeddingsRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _check_datasource(db, datasource_id)
    from engine.semantic.embeddings import EmbeddingService
    api_key = req.api_key if req else None
    api_base = req.api_base if req else None
    model_name = req.model_name if req else None
    service = EmbeddingService(api_key=api_key, api_base=api_base, model_name=model_name)
    res = service.sync_aliases(db, datasource_id)
    if not res.get("success"):
        from engine.policy.error_sanitizer import sanitize_error_message
        safe_res = {**res, "error": sanitize_error_message(str(res.get("error", "")))}
        raise HTTPException(status_code=500, detail=safe_res)
    return res


@router.get("/semantic/aliases/sync-status")
def api_sync_status(datasource_id: str = Query(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    _check_datasource(db, datasource_id)
    aliases = (
        db.query(SemanticAlias)
        .filter(
            SemanticAlias.data_source_id == datasource_id,
            SemanticAlias.target_type != "sensitive"
        )
        .all()
    )
    
    total_count = len(aliases)
    synced_count = 0
    stale_count = 0
    last_sync_at = None
    
    for a in aliases:
        if a.embedding_blob:
            if a.embedding_synced_at:
                if a.updated_at and a.updated_at > a.embedding_synced_at:
                    stale_count += 1
                else:
                    synced_count += 1
                
                if last_sync_at is None or a.embedding_synced_at > last_sync_at:
                    last_sync_at = a.embedding_synced_at
            else:
                stale_count += 1
        else:
            stale_count += 1
            
    return {
        "total_count": total_count,
        "synced_count": synced_count,
        "stale_count": stale_count,
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
    }

