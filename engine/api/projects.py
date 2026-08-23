import logging
import uuid
from typing import Any

from engine.schemas.project import ProjectResponse
from engine.agent.resource_refs import ProjectResourceDescriptor

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.errors import DBFoxError
from engine.models import Project
from engine.projects.service import get_or_create_default_project
from engine.runtime_composition import discover_project_resources
from engine.schemas import ProjectCreateRequest

logger = logging.getLogger("dbfox.api.projects")
router = APIRouter()


def _project_to_dict(project: Project) -> dict[str, Any]:
    return ProjectResponse.model_validate(project).model_dump(mode="json")


@router.get("/projects", response_model=list[ProjectResponse])
def api_list_projects(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        _project, created = get_or_create_default_project(db)
        if created:
            db.commit()

        projects = db.query(Project).filter(Project.status == "active").order_by(Project.created_at.asc()).all()
        return [_project_to_dict(project) for project in projects]
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/resources",
    response_model=list[ProjectResourceDescriptor],
)
def api_list_project_resources(
    project_id: str,
    db: Session = Depends(get_db),
) -> tuple[ProjectResourceDescriptor, ...]:
    project = db.get(Project, project_id)
    if project is None or str(project.status) != "active":
        raise DBFoxError("Project not found", "PROJECT_NOT_FOUND")
    return discover_project_resources(db, project_id)


@router.post("/projects", response_model=ProjectResponse)
def api_create_project(req: ProjectCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    name = req.name.strip()
    if not name:
        raise DBFoxError("Project name is required", "PROJECT_NAME_REQUIRED")

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
        return _project_to_dict(project)
    except Exception:
        db.rollback()
        raise
