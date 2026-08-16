"""Shared ToolAttemptHandler semantics for in-process and isolated attempts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from engine.tools.runtime.attempt import (
    CompositeResourceResolver,
    ToolAttemptRequest,
)
from engine.tools.runtime.base import BaseTool
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.result import ToolResult
from engine.tools.runtime.runtime import ToolRuntime


@dataclass(frozen=True)
class AttemptInvocationRequest:
    datasource_id: str
    datasource_generation: int
    question: str
    session_id: str
    run_id: str
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
    ) -> ToolResult:
        tool = self.registry.require(request.tool_name)
        if not isinstance(tool, BaseTool):
            raise TypeError(
                f"{request.tool_name} is a Runtime control command, not an executable tool"
            )
        if tool.version != request.frozen_tool_version:
            return ToolResult(
                name=request.tool_name,
                status="failed",
                input=dict(request.authorized_input),
                error="The frozen tool contract is no longer current.",
                error_code="TOOL_VERSION_CHANGED",
                latency_ms=0,
            )

        resources = self.resolver.resolve(request.invocation.scope_refs)
        invocation_request = _database_scope_request(request)
        runtime = ToolRuntime(self.registry)
        if request.mode == "reconcile":
            return runtime.reconcile(
                tool_name=request.tool_name,
                raw_input=dict(request.authorized_input),
                request=invocation_request,
                db=resources.get("database"),
                idempotency_key=request.invocation.idempotency_key,
                cancellation_probe=cancellation_probe,
                deadline=deadline,
                scope_refs=request.invocation.scope_refs,
                resources=resources,
            )
        return runtime.invoke(
            tool_name=request.tool_name,
            raw_input=dict(request.authorized_input),
            request=invocation_request,
            db=resources.get("database"),
            idempotency_key=request.invocation.idempotency_key,
            cancellation_probe=cancellation_probe,
            deadline=deadline,
            scope_refs=request.invocation.scope_refs,
            resources=resources,
        )
