"""Canonical Workbench-to-Conversation reference envelope."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.agent.resource_refs import RequestedResourceRef
from engine.json_codec import canonical_dumps as _json, loads as _loads
from engine.resource import RESOURCE_KIND_PATTERN

MAX_INPUT_REFERENCES = 12


class ReferencedObject(BaseModel):
    """Capability-owned object identity; never execution authority by itself."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    kind: str = Field(min_length=3, max_length=64, pattern=RESOURCE_KIND_PATTERN)
    id: str = Field(min_length=1, max_length=512)
    version: str | int | None = None


class ConversationInputReference(BaseModel):
    """One bounded user-visible selection attached to a Conversation Input."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=500)
    authority: RequestedResourceRef | None = None
    object: ReferencedObject | None = None
    locator: str | None = Field(default=None, max_length=1_000)
    artifact_id: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def require_identity(self) -> "ConversationInputReference":
        if self.authority is None and self.object is None and self.artifact_id is None:
            raise ValueError(
                "Conversation reference requires authority, object, or artifact identity"
            )
        return self


def dump_input_references(
    references: tuple[ConversationInputReference, ...],
) -> str:
    if len(references) > MAX_INPUT_REFERENCES:
        raise ValueError(
            f"input reference count {len(references)} exceeds maximum {MAX_INPUT_REFERENCES}"
        )
    return _json([reference.model_dump(mode="json") for reference in references])


def load_input_references(raw_json: str) -> tuple[ConversationInputReference, ...]:
    try:
        raw = _loads(raw_json)
    except Exception as exc:
        raise ValueError(f"malformed references_json: {exc}") from exc
    if not isinstance(raw, list):
        raise ValueError(f"references_json must be a list, got {type(raw).__name__}")
    references = tuple(ConversationInputReference.model_validate(item) for item in raw)
    if len(references) > MAX_INPUT_REFERENCES:
        raise ValueError(
            f"input reference count {len(references)} exceeds maximum {MAX_INPUT_REFERENCES}"
        )
    return references
