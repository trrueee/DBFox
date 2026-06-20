from __future__ import annotations

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
    WorkspaceTableScope,
)
from engine.schemas import (
    WorkspaceTableScopeUpdateRequest,
)
from engine.schemas.semantic import (
    WorkspaceTableScopeResponse,
)

logger = logging.getLogger("dbfox.api.semantic")
router = APIRouter()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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
# NOTE: Semantic Aliases CRUD, Metrics, Dimensions, and Embedding sync
# endpoints were removed in the MVP simplification (2026-06-20).
# The SemanticAlias DB table is kept internally for sensitivity rules
# (engine.policy.sensitivity) and for schema_search_docs enrichment.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Table Scope (workspace feature)
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
