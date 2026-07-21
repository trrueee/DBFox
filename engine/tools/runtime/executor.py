"""Bounded execution control for provider-neutral tools."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable

from engine.tools.runtime.base import BaseTool
from engine.tools.runtime.result import ToolResult


@dataclass(frozen=True)
class ToolExecutionControl:
    deadline: float
    cancelled: threading.Event

    def is_cancelled(self) -> bool:
        return self.cancelled.is_set() or time.monotonic() >= self.deadline


ToolOperation = Callable[[ToolExecutionControl], ToolResult]


class ToolExecutor:
    """Execute a frozen tool contract with timeout, retry and cancellation.

    Operations run on executor-owned threads and must create their database
    Session inside that thread. On timeout/cancel the control is signalled
    before the caller settles the durable ToolInvocation, so a late operation
    must roll back instead of publishing a successful result.
    """

    def __init__(self, *, max_workers: int = 4, poll_interval_seconds: float = 0.05) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dbfox-tool")
        self._poll_interval = max(0.01, poll_interval_seconds)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def execute(
        self,
        *,
        tool: BaseTool,
        scope_key: str,
        operation: ToolOperation,
        should_cancel: Callable[[], bool] | None = None,
        cancel_action: Callable[[], None] | None = None,
        on_attempt: Callable[[int], None] | None = None,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        spec = tool.execution
        if spec.backend != "in_process":
            return ToolResult(
                name=tool.name,
                status="failed",
                error=f"Tool execution backend '{spec.backend}' is unavailable.",
                error_code="TOOL_EXECUTION_BACKEND_UNAVAILABLE",
            )
        timeout = min(float(spec.timeout_seconds), timeout_seconds or float(spec.timeout_seconds))
        attempts = 0
        started = time.monotonic()

        while True:
            attempts += 1
            if on_attempt:
                on_attempt(attempts)
            cancelled = threading.Event()
            control = ToolExecutionControl(deadline=time.monotonic() + timeout, cancelled=cancelled)
            future = self._submit(tool, scope_key, operation, control)
            result = self._await(
                tool_name=tool.name,
                future=future,
                control=control,
                should_cancel=should_cancel,
                cancel_action=cancel_action,
                started=started,
                attempts=attempts,
            )
            if result.status == "success":
                return self._enforce_output_limit(tool, result, attempts)
            can_retry = (
                spec.idempotent
                and spec.retryable
                and attempts <= spec.max_retries
                and result.error_code not in {"TOOL_CANCELLED", "TOOL_TIMEOUT"}
            )
            if not can_retry:
                return result.model_copy(update={"attempts": attempts})

    def _submit(
        self,
        tool: BaseTool,
        scope_key: str,
        operation: ToolOperation,
        control: ToolExecutionControl,
    ) -> Future[ToolResult]:
        lock = self._scope_lock(scope_key) if tool.execution.concurrency == "sequential" else None

        def invoke() -> ToolResult:
            with lock if lock is not None else nullcontext():
                return operation(control)

        return self._pool.submit(invoke)

    def _await(
        self,
        *,
        tool_name: str,
        future: Future[ToolResult],
        control: ToolExecutionControl,
        should_cancel: Callable[[], bool] | None,
        cancel_action: Callable[[], None] | None,
        started: float,
        attempts: int,
    ) -> ToolResult:
        while True:
            if should_cancel and should_cancel():
                return self._stop(
                    tool_name, future, control, cancel_action,
                    code="TOOL_CANCELLED", message="Tool execution was cancelled.",
                    started=started, attempts=attempts,
                )
            remaining = control.deadline - time.monotonic()
            if remaining <= 0:
                return self._stop(
                    tool_name, future, control, cancel_action,
                    code="TOOL_TIMEOUT", message="Tool execution exceeded its deadline.",
                    started=started, attempts=attempts,
                )
            try:
                result = future.result(timeout=min(self._poll_interval, remaining))
                if should_cancel and should_cancel():
                    return self._stop(
                        tool_name, future, control, cancel_action,
                        code="TOOL_CANCELLED", message="Tool execution was cancelled.",
                        started=started, attempts=attempts,
                    )
                if time.monotonic() >= control.deadline:
                    return self._stop(
                        tool_name, future, control, cancel_action,
                        code="TOOL_TIMEOUT", message="Tool execution exceeded its deadline.",
                        started=started, attempts=attempts,
                    )
                return result
            except TimeoutError:
                continue

    @staticmethod
    def _stop(
        tool_name: str,
        future: Future[ToolResult],
        control: ToolExecutionControl,
        cancel_action: Callable[[], None] | None,
        *,
        code: str,
        message: str,
        started: float,
        attempts: int,
    ) -> ToolResult:
        control.cancelled.set()
        future.cancel()
        if cancel_action:
            cancel_action()
        return ToolResult(
            name=tool_name,
            status="failed",
            error=message,
            error_code=code,
            latency_ms=int((time.monotonic() - started) * 1_000),
            attempts=attempts,
        )

    @staticmethod
    def _enforce_output_limit(tool: BaseTool, result: ToolResult, attempts: int) -> ToolResult:
        encoded = json.dumps(result.output or {}, ensure_ascii=False, default=str).encode("utf-8")
        if len(encoded) <= tool.execution.max_output_bytes:
            return result.model_copy(update={"attempts": attempts})
        return ToolResult(
            name=tool.name,
            status="failed",
            input=result.input,
            error="Tool output exceeded its declared byte limit.",
            error_code="TOOL_OUTPUT_TOO_LARGE",
            latency_ms=result.latency_ms,
            attempts=attempts,
        )

    def _scope_lock(self, scope_key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(scope_key, threading.Lock())
