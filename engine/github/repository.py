"""Temporary static GitHub lifecycle facade over the DLC-owned state database.

R5.2 keeps the existing HTTP/runtime surface available, but every durable read
and write is cut over to ``dlcs/data/dbfox.github/state.sqlite3``.  R5.3 removes
this module together with the static GitHub surface.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from engine.github.contracts import GithubInvalidInputError, GithubNotFoundError
from engine.github.migration import GithubBindingRecord, transitional_store
from engine.github.service import (
    normalize_github_repository,
    resolve_public_repository_revision,
)
from engine.models import Project


def list_github_bindings(db: Session, project_id: str) -> list[GithubBindingRecord]:
    """Return target-store bindings ordered by creation time."""
    return transitional_store(db).list_bindings(project_id)


def get_github_binding(
    db: Session,
    project_id: str,
    binding_id: str,
) -> GithubBindingRecord | None:
    """Find one target-store binding scoped strictly to its project."""
    if not project_id or not binding_id:
        return None
    binding = transitional_store(db).get_binding(binding_id)
    return binding if binding is not None and binding.project_id == project_id else None


def create_github_binding(
    db: Session,
    project_id: str,
    repo_input: str,
    ref_name: str = "",
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> GithubBindingRecord:
    """Validate, resolve, and persist a binding only in DLC-owned state."""
    project = db.get(Project, project_id)
    if project is None:
        raise GithubNotFoundError(f"Project not found: {project_id}")

    owner, repository = normalize_github_repository(repo_input)
    revision, effective_ref, default_branch, description = (
        resolve_public_repository_revision(
            owner=owner,
            repository=repository,
            ref_name=(ref_name or "").strip(),
            custom_transport=custom_transport,
            http_client=http_client,
        )
    )
    now = datetime.now()
    binding = GithubBindingRecord(
        id=str(uuid4()),
        project_id=project_id,
        owner=owner,
        repository=repository,
        ref_name=effective_ref,
        resolved_revision=revision,
        default_branch=default_branch,
        description=description,
        created_at=now,
        updated_at=now,
    )
    store = transitional_store(db)
    try:
        store.create_binding(binding)
    except sqlite3.IntegrityError as exc:
        raise GithubInvalidInputError(
            f"Binding for {owner}/{repository}@{effective_ref} already exists in this project."
        ) from exc
    created = store.get_binding(binding.id)
    if created is None:
        raise RuntimeError("Created GitHub binding could not be reloaded")
    return created


def delete_github_binding(
    db: Session,
    project_id: str,
    binding_id: str,
) -> bool:
    """Delete a target-store binding scoped strictly to its project."""
    return transitional_store(db).delete_binding(project_id, binding_id)


def refresh_github_binding(
    db: Session,
    project_id: str,
    binding_id: str,
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> GithubBindingRecord:
    """Refresh one immutable revision and write only DLC-owned state."""
    binding = get_github_binding(db, project_id, binding_id)
    if binding is None:
        raise GithubNotFoundError(
            f"GitHub binding not found in project {project_id}: {binding_id}"
        )

    revision, effective_ref, default_branch, description = (
        resolve_public_repository_revision(
            owner=binding.owner,
            repository=binding.repository,
            ref_name=binding.ref_name,
            custom_transport=custom_transport,
            http_client=http_client,
        )
    )
    updated = replace(
        binding,
        resolved_revision=revision,
        ref_name=effective_ref,
        default_branch=default_branch or binding.default_branch,
        description=description if description is not None else binding.description,
        updated_at=datetime.now(),
    )
    store = transitional_store(db)
    store.update_binding(updated)
    refreshed = store.get_binding(binding_id)
    if refreshed is None:
        raise RuntimeError("Updated GitHub binding could not be reloaded")
    return refreshed
