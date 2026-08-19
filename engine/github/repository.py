"""Persistence and lifecycle operations for GithubRepositoryBinding."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.github.contracts import GithubInvalidInputError, GithubNotFoundError
from engine.github.models import GithubRepositoryBinding
from engine.github.service import (
    normalize_github_repository,
    resolve_public_repository_revision,
)
from engine.models import Project


def list_github_bindings(db: Session, project_id: str) -> list[GithubRepositoryBinding]:
    """Return all GitHub repository bindings for a project ordered by creation time."""
    if not project_id:
        return []
    return list(
        db.execute(
            select(GithubRepositoryBinding)
            .where(GithubRepositoryBinding.project_id == project_id)
            .order_by(GithubRepositoryBinding.created_at.asc())
        ).scalars().all()
    )


def get_github_binding(
    db: Session,
    project_id: str,
    binding_id: str,
) -> GithubRepositoryBinding | None:
    """Find a single GitHub repository binding scoped strictly to its project."""
    if not project_id or not binding_id:
        return None
    return db.execute(
        select(GithubRepositoryBinding).where(
            GithubRepositoryBinding.id == binding_id,
            GithubRepositoryBinding.project_id == project_id,
        )
    ).scalar_one_or_none()


def create_github_binding(
    db: Session,
    project_id: str,
    repo_input: str,
    ref_name: str = "",
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> GithubRepositoryBinding:
    """Validate, resolve, and persist a new GitHub repository binding."""
    project = db.get(Project, project_id)
    if project is None:
        raise GithubNotFoundError(f"Project not found: {project_id}")

    owner, repo = normalize_github_repository(repo_input)
    clean_ref = (ref_name or "").strip()

    # Resolve immutable revision and effective ref (discovering default branch if clean_ref is empty)
    revision, effective_ref, default_branch, description = resolve_public_repository_revision(
        owner=owner,
        repository=repo,
        ref_name=clean_ref,
        custom_transport=custom_transport,
        http_client=http_client,
    )

    # Check for existing binding with the effective ref
    existing = db.execute(
        select(GithubRepositoryBinding).where(
            GithubRepositoryBinding.project_id == project_id,
            GithubRepositoryBinding.owner == owner,
            GithubRepositoryBinding.repository == repo,
            GithubRepositoryBinding.ref_name == effective_ref,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise GithubInvalidInputError(
            f"Binding for {owner}/{repo}@{effective_ref} already exists in this project."
        )

    binding = GithubRepositoryBinding(
        project_id=project_id,
        owner=owner,
        repository=repo,
        ref_name=effective_ref,
        resolved_revision=revision,
        default_branch=default_branch,
        description=description,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def delete_github_binding(
    db: Session,
    project_id: str,
    binding_id: str,
) -> bool:
    """Delete a GitHub repository binding scoped strictly to its project."""
    binding = get_github_binding(db, project_id, binding_id)
    if binding is None:
        return False
    db.delete(binding)
    db.commit()
    return True


def refresh_github_binding(
    db: Session,
    project_id: str,
    binding_id: str,
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> GithubRepositoryBinding:
    """Re-resolve the immutable commit revision for an existing binding."""
    binding = get_github_binding(db, project_id, binding_id)
    if binding is None:
        raise GithubNotFoundError(f"GitHub binding not found in project {project_id}: {binding_id}")

    revision, effective_ref, default_branch, description = resolve_public_repository_revision(
        owner=binding.owner,
        repository=binding.repository,
        ref_name=binding.ref_name,
        custom_transport=custom_transport,
        http_client=http_client,
    )

    binding.resolved_revision = revision
    binding.ref_name = effective_ref
    if default_branch:
        binding.default_branch = default_branch
    if description is not None:
        binding.description = description

    db.commit()
    db.refresh(binding)
    return binding
