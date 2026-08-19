"""Strict typed codec for frozen Input resource refs.

Two real consumers: ContextAssembler and ToolDispatcher.
"""

from __future__ import annotations

from engine.json_codec import canonical_dumps as _json, loads as _loads
from engine.tools.runtime.attempt import ResourceScopeRef

MAX_INPUT_RESOURCE_REFS = 16


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


def load_resource_refs(raw_json: str | None) -> tuple[ResourceScopeRef, ...] | None:
    """Deserialize frozen resource refs from persisted JSON.

    Returns:
        tuple of refs if JSON was non-NULL (including empty tuple for "[]")
        None if JSON was NULL (legacy pre-P4 record)

    Raises:
        ValueError on malformed non-NULL JSON (fail closed)
    """
    if raw_json is None:
        return None
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
