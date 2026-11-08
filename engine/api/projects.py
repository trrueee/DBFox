import logging
import uuid
from typing import Any

from engine.schemas.project import ProjectResponse
from engine.agent.resource_refs import ProjectResourceDescriptor

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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

    description = (req.description or "").strip() or None
    project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dbfox:project:{req.idempotency_key}")) if req.idempotency_key else str(uuid.uuid4())

    def replay() -> dict[str, Any] | None:
        existing = db.get(Project, project_id)
        if existing is None:
            return None
        if existing.name != name or existing.description != description or existing.status != "active":
            raise HTTPException(status_code=409, detail={"code": "PROJECT_CREATE_CONFLICT", "message": "The creation key belongs to a different project."})
        return _project_to_dict(existing)

    prior = replay() if req.idempotency_key else None
    if prior is not None:
        return prior

    try:
        project = Project(
            id=project_id,
            name=name,
            description=description,
            status="active",
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return _project_to_dict(project)
    except IntegrityError:
        db.rollback()
        prior = replay() if req.idempotency_key else None
        if prior is not None:
            return prior
        raise
    except Exception:
        db.rollback()
        raise
