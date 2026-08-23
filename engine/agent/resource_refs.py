"""Strict typed codec for frozen Input resource refs.

Consumers: ContextAssembler, ToolDispatcher, and ProjectResourceProviders.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from engine.json_codec import canonical_dumps as _json, loads as _loads
from engine.resource import ResourceScopeRef

MAX_INPUT_RESOURCE_REFS = 16


class RequestedResourceRef(BaseModel):
    """Wire representation of client resource intent. Excludes version."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=256)


class ProjectResourceDescriptor(BaseModel):
    """Project-scoped resource discovery descriptor with server-canonical freshness version."""

    model_config = ConfigDict(frozen=True)

    kind: str
    id: str
    version: int | str
    name: str
    is_default: bool = False

    def to_scope_ref(self) -> ResourceScopeRef:
        return ResourceScopeRef(kind=self.kind, id=self.id, version=self.version)


class ProjectResourceProvider(Protocol):
    """DLC discovery interface for project-scoped resources."""

    def __call__(self, db: Any, project_id: str) -> tuple[ProjectResourceDescriptor, ...]:
        ...


def dump_resource_refs(refs: tuple[ResourceScopeRef, ...]) -> str:
    """Serialize resource refs to canonical JSON. Validates bounds and uniqueness."""
    if len(refs) > MAX_INPUT_RESOURCE_REFS:
        raise ValueError(
            f"resource_refs count {len(refs)} exceeds maximum {MAX_INPUT_RESOURCE_REFS}"
        )
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = ref.canonical()
        if key in seen:
            raise ValueError(f"duplicate resource ref: {key}")
        seen.add(key)
    return _json([ref.model_dump() for ref in refs])


def load_resource_refs(raw_json: str) -> tuple[ResourceScopeRef, ...]:
    """Deserialize frozen resource refs from persisted JSON.

    Raises:
        ValueError on malformed JSON (fail closed)
    """
    try:
        raw = _loads(raw_json)
    except Exception as exc:
        raise ValueError(f"malformed resource_refs_json: {exc}") from exc
    if not isinstance(raw, list):
        raise ValueError(f"resource_refs_json must be a list, got {type(raw).__name__}")
    refs: list[ResourceScopeRef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"resource ref item must be dict, got {type(item).__name__}")
        if "kind" not in item or "id" not in item:
            raise ValueError(f"resource ref item missing kind/id: {item}")
        refs.append(ResourceScopeRef(**item))
    if len(refs) > MAX_INPUT_RESOURCE_REFS:
        raise ValueError(
            f"resource_refs count {len(refs)} exceeds maximum {MAX_INPUT_RESOURCE_REFS}"
        )
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = ref.canonical()
        if key in seen:
            raise ValueError(f"duplicate resource ref: {key}")
        seen.add(key)
    return tuple(refs)


def resource_refs_for_run(
    db: Any,
    run: Any,
) -> tuple[ResourceScopeRef, ...]:
    """Return one Run's frozen authority from its admitted SessionInput.

    Missing or pre-resource-ref inputs fail closed.  Durable Run compatibility
    fields are never an authority source.
    """

    from engine.models import AgentSessionInput

    input_id = str(getattr(run, "input_id", "") or "")
    if input_id:
        input_row = db.get(AgentSessionInput, input_id)
        if input_row is not None:
            return load_resource_refs(str(input_row.resource_refs_json))
    return ()


def single_run_resource_ref(
    db: Any,
    run: Any,
    kind: str,
) -> ResourceScopeRef | None:
    """Return the unambiguous frozen ref for ``kind`` or ``None``."""

    matches = tuple(
        ref
        for ref in resource_refs_for_run(db, run)
        if ref.kind == kind
    )
    return matches[0] if len(matches) == 1 else None
