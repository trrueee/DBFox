"""Resolve one explicitly authorized database from a Tool Run."""

from __future__ import annotations

from dbfox_dlc_api import ExtensionToolRunContext, ResourceScopeRef, ToolInputError

from .contracts import DatabaseHandle
from .resource_kind import DATABASE_RESOURCE_KIND


def select_database(
    context: ExtensionToolRunContext,
    database_id: str | None,
) -> tuple[ResourceScopeRef, DatabaseHandle]:
    scopes = context.scopes(DATABASE_RESOURCE_KIND)
    if database_id is None:
        if len(scopes) != 1:
            raise ToolInputError(
                "database_id is required when the Run authorizes multiple databases."
            )
        selected = scopes[0]
    else:
        selected = next((ref for ref in scopes if ref.id == database_id), None)
        if selected is None:
            raise ToolInputError("The selected database is not authorized for this Run.")
    resource = context.resource(selected)
    if not isinstance(resource, DatabaseHandle):
        raise RuntimeError("dbfox.data database resource did not resolve to DatabaseHandle")
    return selected, resource
