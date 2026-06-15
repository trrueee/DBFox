import logging
from sqlalchemy.orm import Session
from fastapi import HTTPException

from engine.models import DEFAULT_PROJECT_ID, DEFAULT_PROJECT_NAME, Project

logger = logging.getLogger("databox.projects.service")


def get_or_create_default_project(db: Session) -> Project:
    """Get or auto-create the default workspace project."""
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


def resolve_project_id(db: Session, project_id: str | None) -> str:
    """Resolve and validate active project ID or fallback to default."""
    if not project_id:
        return str(get_or_create_default_project(db).id)
    if project_id == DEFAULT_PROJECT_ID:
        return str(get_or_create_default_project(db).id)

    project = db.query(Project).filter(Project.id == project_id, Project.status == "active").first()
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})
    return str(project.id)
