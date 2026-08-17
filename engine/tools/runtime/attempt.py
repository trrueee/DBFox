"""Serializable attempt contract for the Tool execution resource seam.

This module defines the smallest wire-safe value boundary shared by
in-process and isolated-process attempts. It deliberately excludes callables,
SQLAlchemy Sessions, HTTP clients, Secret objects, and arbitrary metadata
bags. Database + Workspace resources prove the boundary before any additional
grant type is added.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from engine.tools.runtime.result import ToolResult


class ResourceScopeRef(BaseModel):
    """Stable identity of one authorized execution resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=256)
    version: str | int | None = Field(default=None)
    location: str | None = Field(default=None, max_length=4_096)

    def canonical(self) -> tuple[str, str]:
        return (self.kind, self.id)


class ToolInvocationContext(BaseModel):
    """Serializable invocation facts required to execute one attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    run_id: str
    turn_id: str
    invocation_id: str
    idempotency_key: str
    deadline_at: datetime | None = None
    scope_refs: tuple[ResourceScopeRef, ...] = ()

    @model_validator(mode="after")
    def validate_unique_scopes(self) -> "ToolInvocationContext":
        keys = [ref.canonical() for ref in self.scope_refs]
        if len(set(keys)) != len(keys):
            raise ValueError("scope_refs must be unique by (kind, id)")
        return self

    def scope(self, kind: str) -> ResourceScopeRef | None:
        return next(
            (ref for ref in self.scope_refs if ref.kind == kind),
            None,
        )


class ToolAttemptRequest(BaseModel):
    """One attempt at executing or reconciling a frozen Tool contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["execute", "reconcile"]
    tool_name: str
    frozen_tool_declared_version: str
    frozen_tool_contract_hash: str
    invocation: ToolInvocationContext
    authorized_input: dict[str, JsonValue]
    attempt_timeout_ms: int = Field(ge=1, le=3_600_000)


class ScopedResourceResolver(Protocol):
    """Resolve one scope ref into an authorized typed resource value.

    Implementations are capability-specific and never expose a global
    container to Tool handlers.
    """

    def __call__(self, ref: ResourceScopeRef) -> Any: ...


class CompositeResourceResolver:
    """Immutable composition of capability-owned scope resolvers."""

    def __init__(self) -> None:
        self._resolvers: dict[str, ScopedResourceResolver] = {}
        self._frozen = False

    def register(
        self,
        kind: str,
        resolver: ScopedResourceResolver,
    ) -> "CompositeResourceResolver":
        if self._frozen:
            raise RuntimeError("Resource resolver registry is frozen.")
        if not kind.strip():
            raise ValueError("Resource scope kind must not be empty")
        if kind in self._resolvers:
            raise ValueError(f"Resource scope kind is already registered: {kind}")
        self._resolvers[kind] = resolver
        return self

    def freeze(self) -> "CompositeResourceResolver":
        self._frozen = True
        return self

    def resolve(self, refs: tuple[ResourceScopeRef, ...]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for ref in refs:
            resolver = self._resolvers.get(ref.kind)
            if resolver is None:
                raise KeyError(
                    f"No resolver is registered for resource scope kind {ref.kind!r}"
                )
            resolved[ref.kind] = resolver(ref)
        return resolved


class ToolAttemptHandler(Protocol):
    """Shared execution semantics for in-process and isolated attempts."""

    def run(self, request: ToolAttemptRequest) -> ToolResult: ...
