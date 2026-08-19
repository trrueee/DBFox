"""FastAPI router for GitHub DLC repository bindings and file exploration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from engine.db import get_db
from engine.github.contracts import (
    CreateGithubBindingRequest,
    GithubBindingResponse,
    GithubFileContentResponse,
    GithubFileListResponse,
    GithubInvalidInputError,
    GithubNotFoundError,
    GithubPrivateRepoError,
    GithubRateLimitedError,
    GithubServiceError,
)
from engine.github.models import GithubRepositoryBinding
from engine.github.repository import (
    create_github_binding,
    delete_github_binding,
    get_github_binding,
    list_github_bindings,
    refresh_github_binding,
)
from engine.github.service import GithubReadService

router = APIRouter(prefix="/projects/{project_id}/github", tags=["github"])


def _to_binding_response(b: GithubRepositoryBinding) -> GithubBindingResponse:
    return GithubBindingResponse(
        id=str(b.id),
        project_id=str(b.project_id),
        owner=str(b.owner),
        repository=str(b.repository),
        ref_name=str(b.ref_name),
        resolved_revision=str(b.resolved_revision),
        default_branch=b.default_branch,
        description=b.description,
        created_at=b.created_at.isoformat() if b.created_at else "",
        updated_at=b.updated_at.isoformat() if b.updated_at else "",
    )


@router.get("/bindings", response_model=list[GithubBindingResponse])
def get_bindings(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[GithubBindingResponse]:
    """List all GitHub repository bindings in a project."""
    bindings = list_github_bindings(db, project_id)
    return [_to_binding_response(b) for b in bindings]


@router.post("/bindings", response_model=GithubBindingResponse, status_code=status.HTTP_201_CREATED)
def create_binding(
    project_id: str,
    req: CreateGithubBindingRequest,
    db: Session = Depends(get_db),
) -> GithubBindingResponse:
    """Add a new public GitHub repository binding to a project."""
    try:
        binding = create_github_binding(
            db=db,
            project_id=project_id,
            repo_input=req.repository,
            ref_name=req.ref_name,
        )
        return _to_binding_response(binding)
    except GithubInvalidInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GithubPrivateRepoError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Private repositories are not supported in public read-only mode.",
        ) from exc
    except GithubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GithubRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GithubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.delete(
    "/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_binding_route(
    project_id: str,
    binding_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a GitHub repository binding within the scoped project."""
    success = delete_github_binding(db, project_id, binding_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")


@router.post("/bindings/{binding_id}/refresh", response_model=GithubBindingResponse)
def refresh_binding_route(
    project_id: str,
    binding_id: str,
    db: Session = Depends(get_db),
) -> GithubBindingResponse:
    """Refresh the resolved immutable commit revision for an existing binding."""
    try:
        binding = refresh_github_binding(db, project_id, binding_id)
        return _to_binding_response(binding)
    except GithubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GithubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/bindings/{binding_id}/files", response_model=GithubFileListResponse)
def list_binding_files(
    project_id: str,
    binding_id: str,
    path: str = Query(default="", description="Repository-relative directory path"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> GithubFileListResponse:
    """List directory contents at the binding's resolved revision."""
    binding = get_github_binding(db, project_id, binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")

    service = GithubReadService(
        owner=binding.owner,
        repository=binding.repository,
        revision=binding.resolved_revision,
        binding_id=binding.id,
        ref_name=binding.ref_name,
    )
    try:
        entries, truncated = service.list_files(path=path, limit=limit)
        return GithubFileListResponse(
            path=path,
            revision=binding.resolved_revision,
            entries=entries,
            truncated=truncated,
        )
    except GithubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/bindings/{binding_id}/file", response_model=GithubFileContentResponse)
def read_binding_file(
    project_id: str,
    binding_id: str,
    path: str = Query(..., min_length=1, description="Repository-relative file path"),
    db: Session = Depends(get_db),
) -> GithubFileContentResponse:
    """Read a text file at the binding's resolved revision for the Dock view."""
    binding = get_github_binding(db, project_id, binding_id)
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")

    service = GithubReadService(
        owner=binding.owner,
        repository=binding.repository,
        revision=binding.resolved_revision,
        binding_id=binding.id,
        ref_name=binding.ref_name,
    )
    try:
        norm_path, rev, size, sha256, content, truncated, _blob = service.read_file(path)
        return GithubFileContentResponse(
            path=norm_path,
            revision=rev,
            size_bytes=size,
            content_sha256=sha256,
            content=content,
            truncated=truncated,
        )
    except GithubNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GithubServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
