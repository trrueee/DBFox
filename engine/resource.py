"""Provider-neutral identity for one authorized Runtime resource."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class ResourceScopeRef(BaseModel):
    """Stable identity and freshness fence for one execution resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=256)
    version: str | int | None = Field(default=None)

    def canonical(self) -> tuple[str, str]:
        return (self.kind, self.id)


# Resource identity is never the kind alone: one Run may authorize multiple
# databases, repositories, or other resources from the same capability.
ResourceKey: TypeAlias = tuple[str, str]
