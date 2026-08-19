"""Project resource discovery provider and execution resolver for github.repository."""

from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.github.models import GithubRepositoryBinding
from engine.github.service import GithubReadService
from engine.tools.runtime.attempt import ResourceScopeRef


def list_github_resources(
    db: Session,
    project_id: str,
) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover all active GitHub repository bindings belonging to a project."""
    if not project_id:
        return ()

    bindings = (
        db.execute(
            select(GithubRepositoryBinding)
            .where(GithubRepositoryBinding.project_id == project_id)
            .order_by(GithubRepositoryBinding.created_at.asc())
        )
        .scalars()
        .all()
    )

    return tuple(
        ProjectResourceDescriptor(
            kind="github.repository",
            id=str(b.id),
            version=str(b.resolved_revision),
            name=f"{b.owner}/{b.repository}",
        )
        for b in bindings
    )


def resolve_github_repository(
    db: Session,
    ref: ResourceScopeRef,
    *,
    custom_transport: Any = None,
) -> GithubReadService:
    """Resolve and freshness-check a github.repository ResourceScopeRef against durable state."""
    if ref.kind != "github.repository":
        raise KeyError(f"Unexpected resource kind: {ref.kind}")

    binding = db.get(GithubRepositoryBinding, str(ref.id))
    if binding is None:
        raise ValueError(f"GitHub repository binding '{ref.id}' does not exist.")

    if binding.resolved_revision != str(ref.version):
        raise ValueError(
            f"GitHub repository binding '{ref.id}' revision ({binding.resolved_revision}) "
            f"does not match authorized execution scope ({ref.version})."
        )

    return GithubReadService(
        owner=binding.owner,
        repository=binding.repository,
        revision=str(ref.version),
        binding_id=str(binding.id),
        custom_transport=custom_transport,
    )
