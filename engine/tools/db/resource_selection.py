"""Select one database from the exact resource set frozen for a Tool attempt."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from engine.errors import ToolInputError
from engine.resource import ResourceScopeRef
from engine.tools.runtime.context import ToolRunContext
from dlcs.dbfox_data.backend.resource_kind import DATABASE_RESOURCE_KIND


@dataclass(frozen=True, slots=True)
class SelectedDatabase:
    ref: ResourceScopeRef
    metadata: Session

    @property
    def id(self) -> str:
        return self.ref.id

    def require_legacy_generation(self) -> int:
        """Return the current built-in DataSource generation at its driver boundary."""

        if not isinstance(self.ref.version, int):
            raise ToolInputError(
                "This database resource requires the dbfox.data execution tools."
            )
        return self.ref.version


def select_database(
    context: ToolRunContext,
    database_id: str | None,
) -> SelectedDatabase:
    """Resolve explicit selection, allowing omission only for one authorized DB."""

    refs = context.scopes(DATABASE_RESOURCE_KIND)
    if not refs:
        raise ToolInputError("This tool requires an authorized database resource.")

    ref: ResourceScopeRef | None
    if database_id is None:
        if len(refs) != 1:
            raise ToolInputError(
                "database_id is required when more than one database is authorized."
            )
        ref = refs[0]
    else:
        ref = next((item for item in refs if item.id == database_id), None)
        if ref is None:
            raise ToolInputError(
                "The selected database is not authorized for this Run."
            )
    assert ref is not None

    resource = context.resource(ref)
    metadata = context.metadata_session
    if metadata is None and isinstance(resource, Session):
        # This is the current built-in Data resource contract. System DLC Data
        # tools receive their own typed DatabaseHandle instead.
        metadata = resource
    if metadata is None:
        raise RuntimeError("The database tool requires the core metadata session")
    return SelectedDatabase(ref=ref, metadata=metadata)
