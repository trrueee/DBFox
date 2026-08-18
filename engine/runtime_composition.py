"""Explicit compile-time composition of DBFox's built-in product capabilities.

This module is the sole backend product-composition root.  It assembles the
existing typed Tool, resource, Context and Completion contracts without a
plugin manager, manifest, container, or additional contribution model.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.orm import Session

from engine.agent.completion import CompletionPolicy
from engine.agent.completion_data import DataCompletionSupport, DataResultCitationConstraint
from engine.agent.context_fragment import ContextContributor
from engine.agent.workspace_context import WorkspaceContextContributor
from engine.db import SessionLocal
from engine.tools.builtin.registry import (
    register_conversation_functions,
    register_core_functions,
    register_data_extension,
    register_remote_job_extension,
    register_workspace_extension,
    register_workspace_write_extension,
)
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ResourceScopeRef,
    ScopedResourceResolver,
)
from engine.workspace.read_service import WorkspaceReadService

if TYPE_CHECKING:
    from engine.agent.loop import RunLoop


def build_product_tool_registry() -> ToolRegistry:
    """Build the complete frozen Tool Registry for the DBFox product."""

    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    register_core_functions(registry)
    register_conversation_functions(registry)
    register_data_extension(registry)
    register_workspace_extension(registry)
    register_workspace_write_extension(registry)
    register_remote_job_extension(registry)
    return registry.freeze()


def build_attempt_resource_resolver() -> CompositeResourceResolver:
    """Build unchanged default Database and Workspace attempt resolvers."""

    resolver = CompositeResourceResolver()

    def resolve_database(_ref: ResourceScopeRef) -> Any:
        # The worker process is short-lived; ToolRuntime/leaf tools manage
        # commit/rollback on this Session, and process exit closes it.
        return SessionLocal()

    def resolve_workspace(ref: ResourceScopeRef) -> WorkspaceReadService:
        if ref.kind != "workspace":
            raise KeyError(ref.kind)
        if not ref.location:
            raise ValueError("Workspace scope is missing its authorized root")
        return WorkspaceReadService(ref.location)

    resolver.register("database", cast(ScopedResourceResolver, resolve_database))
    resolver.register("workspace", cast(ScopedResourceResolver, resolve_workspace))
    return resolver.freeze()


def default_context_contributors() -> tuple[Callable[[Session], ContextContributor], ...]:
    """Return the built-in contributors; Context Kernel owns their use."""

    return (WorkspaceContextContributor,)


def build_default_completion_policy() -> CompletionPolicy:
    """Compose the current Data completion contributions for DBFox."""

    return CompletionPolicy(
        constraints=(DataResultCitationConstraint(),),
        support=DataCompletionSupport(),
    )


def build_product_run_loop(*, session_factory: Callable[[], Session]) -> RunLoop:
    """Construct the production RunLoop with explicit product contributions."""

    from engine.agent.completion import CompletionGate
    from engine.agent.loop import RunLoop

    return RunLoop(
        session_factory=session_factory,
        registry=build_product_tool_registry(),
        context_contributors=default_context_contributors(),
        completion=CompletionGate(build_default_completion_policy()),
    )
