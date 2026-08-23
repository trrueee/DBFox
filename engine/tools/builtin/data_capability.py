"""Legacy in-tree Data capability contributions pending the DLC execution cutover.

This module is the single temporary ownership boundary for Data-domain runtime
contributions that still execute from the frozen Sidecar.  Kernel composition
must consume only the generic contribution contracts returned here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from engine.agent.completion import (
    CompletionConstraint,
    CompletionSupport,
    SemanticArtifactCompletionSupport,
    SemanticCitationConstraint,
)
from engine.agent.resource_refs import ProjectResourceDescriptor, ProjectResourceProvider
from engine.models import DataSource
from engine.resource import ResourceScopeRef
from dlcs.dbfox_data.backend.resource_kind import DATABASE_RESOURCE_KIND


def discover_project_databases(
    db: Session,
    project_id: str,
) -> tuple[ProjectResourceDescriptor, ...]:
    """Discover legacy database resources owned by one Project."""

    if db is None or not project_id:
        return ()
    datasources = (
        db.query(DataSource)
        .filter(DataSource.project_id == project_id)
        .order_by(DataSource.created_at.asc())
        .all()
    )
    return tuple(
        ProjectResourceDescriptor(
            kind=DATABASE_RESOURCE_KIND,
            id=str(datasource.id),
            version=int(datasource.connection_generation or 0),
            name=datasource.name or "Database",
        )
        for datasource in datasources
    )


def resolve_database_metadata_session(
    db: Session,
    _ref: ResourceScopeRef,
) -> Session:
    """Expose the attempt metadata session to legacy in-tree Data tools."""

    return db


def legacy_data_resource_providers() -> tuple[ProjectResourceProvider, ...]:
    return (discover_project_databases,)


def legacy_data_resource_resolvers() -> tuple[
    tuple[
        str,
        Callable[[Session, ResourceScopeRef], Any],
        Literal["metadata_session"],
    ],
    ...,
]:
    return ((DATABASE_RESOURCE_KIND, resolve_database_metadata_session, "metadata_session"),)


def legacy_data_completion_constraints() -> tuple[CompletionConstraint, ...]:
    return (
        SemanticCitationConstraint(
            id="dbfox.data.result_citation",
            semantic_capability="query_result",
        ),
    )


def legacy_data_completion_supports() -> tuple[CompletionSupport, ...]:
    return (
        SemanticArtifactCompletionSupport(
            id="dbfox.data.query_result",
            semantic_capability="query_result",
        ),
    )


def legacy_data_credential_reference_probe(
    db: Session,
    credential_refs: frozenset[str],
) -> bool:
    """Report whether legacy Data state durably owns every supplied reference."""

    if not credential_refs:
        return False
    rows = db.execute(
        select(
            DataSource.password_credential_id,
            DataSource.ssh_password_credential_id,
            DataSource.ssh_key_passphrase_credential_id,
        )
        .where(
            or_(
                DataSource.password_credential_id.in_(credential_refs),
                DataSource.ssh_password_credential_id.in_(credential_refs),
                DataSource.ssh_key_passphrase_credential_id.in_(credential_refs),
            )
        )
    ).all()
    owned = {
        str(value)
        for row in rows
        for value in row
        if value is not None and str(value) in credential_refs
    }
    return owned == credential_refs
