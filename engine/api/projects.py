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


def _datasource_to_dict(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "project_id": ds.project_id or DEFAULT_PROJECT_ID,
        "environment_id": ds.environment_id,
        "name": ds.name,
        "db_type": ds.db_type or "mysql",
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "connection_mode": ds.connection_mode,
        "is_read_only": bool(ds.is_read_only),
        "env": ds.env or "dev",
        "status": ds.status,
        "ssh_enabled": bool(ds.ssh_enabled),
        "ssh_host": ds.ssh_host or "",
        "ssh_port": ds.ssh_port or 22,
        "ssh_username": ds.ssh_username or "",
        "ssh_pkey_path": ds.ssh_pkey_path or "",
        "ssl_enabled": bool(ds.ssl_enabled),
        "ssl_ca_path": ds.ssl_ca_path or "",
        "ssl_cert_path": ds.ssl_cert_path or "",
        "ssl_key_path": ds.ssl_key_path or "",
        "ssl_verify_identity": bool(ds.ssl_verify_identity),
        "last_test_at": ds.last_test_at.isoformat() if ds.last_test_at else None,
        "last_test_status": ds.last_test_status,
        "last_test_error": ds.last_test_error,
        "last_sync_at": ds.last_sync_at.isoformat() if ds.last_sync_at else None,
        "last_sync_status": ds.last_sync_status,
        "last_sync_error": ds.last_sync_error,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
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


