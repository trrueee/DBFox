"""Provider-neutral identity for one authorized Runtime resource."""

from __future__ import annotations

import re
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field


RESOURCE_KIND_PATTERN = r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"
_RESOURCE_KIND_RE = re.compile(RESOURCE_KIND_PATTERN)


def is_namespaced_resource_kind(kind: str) -> bool:
    return bool(_RESOURCE_KIND_RE.fullmatch(kind))


class ResourceScopeRef(BaseModel):
    """Stable identity and freshness fence for one execution resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=3, max_length=64, pattern=RESOURCE_KIND_PATTERN)
    id: str = Field(min_length=1, max_length=256)
    version: str | int | None = Field(default=None)

    def canonical(self) -> tuple[str, str]:
        return (self.kind, self.id)


# Resource identity is never the kind alone: one Run may authorize multiple
# databases, repositories, or other resources from the same capability.
ResourceKey: TypeAlias = tuple[str, str]
