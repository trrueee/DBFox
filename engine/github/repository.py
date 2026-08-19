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


def get_github_binding(db: Session, binding_id: str) -> GithubRepositoryBinding | None:
    """Find a single GitHub repository binding by primary key."""
    if not binding_id:
        return None
    return db.get(GithubRepositoryBinding, binding_id)


def create_github_binding(
    db: Session,
    project_id: str,
    repo_input: str,
    ref_name: str = "main",
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> GithubRepositoryBinding:
    """Validate, resolve, and persist a new GitHub repository binding."""
    project = db.get(Project, project_id)
    if project is None:
        raise GithubNotFoundError(f"Project not found: {project_id}")

    owner, repo = normalize_github_repository(repo_input)
    clean_ref = (ref_name or "main").strip()

    # Check for existing binding
    existing = db.execute(
        select(GithubRepositoryBinding).where(
            GithubRepositoryBinding.project_id == project_id,
            GithubRepositoryBinding.owner == owner,
            GithubRepositoryBinding.repository == repo,
            GithubRepositoryBinding.ref_name == clean_ref,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise GithubInvalidInputError(
            f"Binding for {owner}/{repo}@{clean_ref} already exists in this project."
        )

    # Resolve immutable revision from GitHub
    revision, default_branch, description = resolve_public_repository_revision(
        owner=owner,
        repository=repo,
        ref_name=clean_ref,
        custom_transport=custom_transport,
        http_client=http_client,
    )

    binding = GithubRepositoryBinding(
        project_id=project_id,
        owner=owner,
        repository=repo,
        ref_name=clean_ref,
        resolved_revision=revision,
        default_branch=default_branch,
        description=description,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return binding


def delete_github_binding(db: Session, binding_id: str) -> bool:
    """Delete a GitHub repository binding."""
    binding = db.get(GithubRepositoryBinding, binding_id)
    if binding is None:
        return False
    db.delete(binding)
    db.commit()
    return True


def refresh_github_binding(
    db: Session,
    binding_id: str,
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> GithubRepositoryBinding:
    """Re-resolve the immutable commit revision for an existing binding."""
    binding = db.get(GithubRepositoryBinding, binding_id)
    if binding is None:
        raise GithubNotFoundError(f"GitHub binding not found: {binding_id}")

    revision, default_branch, description = resolve_public_repository_revision(
        owner=binding.owner,
        repository=binding.repository,
        ref_name=binding.ref_name,
        custom_transport=custom_transport,
        http_client=http_client,
    )

    binding.resolved_revision = revision
    if default_branch:
        binding.default_branch = default_branch
    if description is not None:
        binding.description = description

    db.commit()
    db.refresh(binding)
    return binding
