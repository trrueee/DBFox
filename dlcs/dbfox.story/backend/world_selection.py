"""Resolve the explicitly authorized story world from a Tool Run."""

from __future__ import annotations

from dbfox_dlc_api import ExtensionToolRunContext, ResourceScopeRef, ToolInputError

from .store import WorldHandle
from .resource_kind import STORY_WORLD_KIND


def select_world(
    context: ExtensionToolRunContext,
    world_id: str | None,
) -> tuple[ResourceScopeRef, WorldHandle]:
    scopes = context.scopes(STORY_WORLD_KIND)
    if world_id is None:
        if len(scopes) != 1:
            raise ToolInputError(
                "world_id is required when the Run authorizes multiple story worlds."
            )
        selected = scopes[0]
    else:
        selected = next((ref for ref in scopes if ref.id == world_id), None)
        if selected is None:
            raise ToolInputError("The selected story world is not authorized for this Run.")
    resource = context.resource(selected)
    if not isinstance(resource, WorldHandle):
        raise RuntimeError("dbfox.story world resource did not resolve to WorldHandle")
    return selected, resource
