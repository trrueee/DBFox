"""Attempt transport seam.

ToolExecutor remains the only owner of retry/deadline/recovery. A runner only
moves one serializable ToolAttemptRequest to a thread or worker process.
"""

from __future__ import annotations

from typing import Protocol

from engine.tools.runtime.attempt import ToolAttemptRequest
from engine.tools.runtime.result import ToolResult


class ToolExecutionControlLike(Protocol):
    def is_cancelled(self) -> bool: ...

    @property
    def deadline(self) -> float: ...


class ToolAttemptRunner(Protocol):
    def run(
        self,
        *,
        request: ToolAttemptRequest,
        control: ToolExecutionControlLike,
    ) -> ToolResult: ...


class InProcessAttemptRunner:
    """Run one attempt in the executor-owned thread via the shared handler."""

    def __init__(self, handler) -> None:
        self.handler = handler

    def run(
        self,
        *,
        request: ToolAttemptRequest,
        control: ToolExecutionControlLike,
    ) -> ToolResult:
        if control.is_cancelled():
            return ToolResult(
                name=request.tool_name,
                status="failed",
                input=dict(request.authorized_input),
                error="Tool execution was cancelled.",
                error_code="TOOL_CANCELLED",
                latency_ms=0,
            )
        result = self.handler.run(
            request,
            cancellation_probe=control.is_cancelled,
            deadline=control.deadline,
        )
        if control.is_cancelled() and result.status == "success":
            return result.model_copy(
                update={
                    "status": "failed",
                    "output": None,
                    "artifact_drafts": [],
                    "error": "Tool execution was cancelled.",
                    "error_code": "TOOL_CANCELLED",
                }
            )
        return result


class IsolatedProcessAttemptRunner:
    """Skeleton for the P6 worker transport.

    Wire/worker protocol validation and process-tree lifecycle will be added
    when a capability actually requires isolated_process; P7 file_read remains
    in_process with a bounded, root-contained read service.
    """

    protocol_version = 1

    def __init__(self, worker_command: tuple[str, ...]) -> None:
        if not worker_command:
            raise ValueError("isolated worker command must not be empty")
        self.worker_command = worker_command

    def run(
        self,
        *,
        request: ToolAttemptRequest,
        control: ToolExecutionControlLike,
    ) -> ToolResult:
        return ToolResult(
            name=request.tool_name,
            status="failed",
            input=dict(request.authorized_input),
            error="Isolated attempt transport is not available yet.",
            error_code="TOOL_EXECUTION_BACKEND_UNAVAILABLE",
            latency_ms=0,
        )
