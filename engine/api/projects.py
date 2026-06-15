import logging
import uuid
import sys
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DataBoxError
from engine.models import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    DataSource,
    Project,
)
from engine.schemas import ProjectCreateRequest

logger = logging.getLogger("databox.api.projects")
router = APIRouter()


def _project_to_dict(project: Project, datasource_count: int = 0) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "status": project.status,
        "datasource_count": datasource_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _get_or_create_default_project(db: Session) -> Project:
    project = db.query(Project).filter(Project.id == DEFAULT_PROJECT_ID).first()
    if project:
        return project

    project = Project(
        id=DEFAULT_PROJECT_ID,
        name=DEFAULT_PROJECT_NAME,
        description="Auto-created workspace for existing DataBox assets.",
        status="active",
    )
    db.add(project)
    db.flush()
    return project


def _resolve_project_id(db: Session, project_id: str | None) -> str:
    if not project_id:
        return str(_get_or_create_default_project(db).id)
    if project_id == DEFAULT_PROJECT_ID:
        return str(_get_or_create_default_project(db).id)

    project = db.query(Project).filter(Project.id == project_id, Project.status == "active").first()
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})
    return str(project.id)


@router.get("/projects")
def api_list_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _get_or_create_default_project(db)
    db.commit()

    projects = db.query(Project).filter(Project.status == "active").order_by(Project.created_at.asc()).all()
    datasource_counts: dict[str, int] = {}
    for ds in db.query(DataSource).filter(DataSource.project_id.isnot(None)).all():
        datasource_counts[str(ds.project_id)] = datasource_counts.get(str(ds.project_id), 0) + 1

    return [_project_to_dict(project, datasource_counts.get(str(project.id), 0)) for project in projects]


@router.post("/projects")
def api_create_project(req: ProjectCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"code": "PROJECT_NAME_REQUIRED", "message": "Project name is required"})

    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        description=(req.description or "").strip() or None,
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project, 0)


