"""Shared ToolAttemptHandler semantics for in-process and isolated attempts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ToolAttemptRequest,
)
from engine.tools.materialization import current_tool_contract_hash
from engine.tools.runtime.base import BaseTool, ToolRecoveryPolicy
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.result import ToolResult
from engine.tools.runtime.runtime import ToolRuntime

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class AttemptInvocationRequest:
    datasource_id: str
    datasource_generation: int
    question: str
    session_id: str
    run_id: str
    turn_id: str
    execution_id: str


def _database_scope_request(request: ToolAttemptRequest) -> AttemptInvocationRequest:
    database = request.invocation.scope("database")
    datasource_id = database.id if database is not None else ""
    generation = int(database.version or 0) if database is not None else 0
    return AttemptInvocationRequest(
        datasource_id=datasource_id,
        datasource_generation=generation,
        question=f"Isolated tool attempt {request.tool_name}",
        session_id=request.invocation.session_id,
        run_id=request.invocation.run_id,
        turn_id=request.invocation.turn_id,
        execution_id=f"attempt:{request.invocation.invocation_id}",
    )


class ToolAttemptHandler:
    """Verify a frozen contract, resolve authorized scopes, run one attempt."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        resolver: CompositeResourceResolver,
    ) -> None:
        self.registry = registry
        self.resolver = resolver

    def run(
        self,
        request: ToolAttemptRequest,
        *,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
        metadata_session: Session | None = None,
    ) -> ToolResult:
        tool = self._resolve_tool(request)
        if isinstance(tool, ToolResult):
            return tool
        resources = self.resolver.resolve(request.invocation.scope_refs)
        return self._invoke(
            request,
            tool,
            resources,
            cancellation_probe=cancellation_probe,
            deadline=deadline,
            execution_authority=None,
            metadata_session=metadata_session,
        )

    def run_with_resources(
        self,
        request: ToolAttemptRequest,
        resources: dict[str, Any],
        *,
        cancellation_probe: Callable[[], bool] | None = None,
        deadline: float | None = None,
        execution_authority: Any | None = None,
        metadata_session: Session | None = None,
    ) -> ToolResult:
        tool = self._resolve_tool(request)
        if isinstance(tool, ToolResult):
            return tool
        return self._invoke(
            request,
            tool,
            resources,
            cancellation_probe=cancellation_probe,
            deadline=deadline,
            execution_authority=execution_authority,
            metadata_session=metadata_session,
        )

    def _resolve_tool(self, request: ToolAttemptRequest) -> BaseTool | ToolResult:
        tool = self.registry.require(request.tool_name)
        if not isinstance(tool, BaseTool):
            raise TypeError(
                f"{request.tool_name} is a Runtime control command, not an executable tool"
            )
        contract_changed = (
            current_tool_contract_hash(tool) != request.frozen_tool_contract_hash
        )
        # Reconciliation never replays an action.  A policy or presentation
        # change must not prevent a RECONCILE-capable tool from determining the
        # outcome of an already-started external action; the dispatcher has
        # already verified the frozen reconciliation contract before this
        # worker boundary.  Executions still require an exact current contract.
        if contract_changed and not (
            request.mode == "reconcile"
            and tool.execution.recovery == ToolRecoveryPolicy.RECONCILE
        ):
            return ToolResult(
                name=request.tool_name,
                status="failed",
                input=dict(request.authorized_input),
                error="The frozen tool contract hash is no longer current.",
                error_code="TOOL_VERSION_CHANGED",
                latency_ms=0,
            )
        return tool

    def _invoke(
        self,
        request: ToolAttemptRequest,
        tool: BaseTool,
        resources: dict[str, Any],
        *,
        cancellation_probe: Callable[[], bool] | None,
        deadline: float | None,
        execution_authority: Any | None,
        metadata_session: Session | None = None,
    ) -> ToolResult:
        invocation_request = _database_scope_request(request)
        runtime = ToolRuntime(self.registry)
        if request.mode == "reconcile":
            return runtime.reconcile(
                tool_name=request.tool_name,
                raw_input=dict(request.authorized_input),
                request=invocation_request,
                idempotency_key=request.invocation.idempotency_key,
                cancellation_probe=cancellation_probe,
                deadline=deadline,
                execution_authority=execution_authority,
                scope_refs=request.invocation.scope_refs,
                resources=resources,
                metadata_session=metadata_session,
            )
        return runtime.invoke(
            tool_name=request.tool_name,
            raw_input=dict(request.authorized_input),
            request=invocation_request,
            idempotency_key=request.invocation.idempotency_key,
            cancellation_probe=cancellation_probe,
            deadline=deadline,
            execution_authority=execution_authority,
            scope_refs=request.invocation.scope_refs,
            resources=resources,
            metadata_session=metadata_session,
        )
