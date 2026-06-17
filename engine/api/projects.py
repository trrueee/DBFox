import logging
import uuid
import sys
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    DataSource,
    Project,
)
from engine.schemas import ProjectCreateRequest

logger = logging.getLogger("dbfox.api.projects")
router = APIRouter()


def _project_to_dict(project: Project, datasource_count: int = 0) -> dict[str, Any]:
    from engine.schemas.project import ProjectResponse
    result = ProjectResponse.model_validate(project).model_dump(mode="json")
    result["datasource_count"] = datasource_count
    return result


from engine.projects.service import get_or_create_default_project


@router.get("/projects")
def api_list_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        get_or_create_default_project(db)
        db.commit()

        projects = db.query(Project).filter(Project.status == "active").order_by(Project.created_at.asc()).all()
        datasource_counts = {
            str(project_id): int(count)
            for project_id, count in (
                db.query(DataSource.project_id, func.count(DataSource.id))
                .filter(DataSource.project_id.isnot(None))
                .group_by(DataSource.project_id)
                .all()
            )
        }

        return [_project_to_dict(project, datasource_counts.get(str(project.id), 0)) for project in projects]
    except Exception:
        db.rollback()
        raise


@router.post("/projects")
def api_create_project(req: ProjectCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"code": "PROJECT_NAME_REQUIRED", "message": "Project name is required"})

    try:
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
    except Exception:
        db.rollback()
        raise


