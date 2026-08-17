"""Bounded execution control for provider-neutral tools."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Callable, Generic, Sequence, TypeVar

from engine.json_codec import byte_size
from engine.tools.runtime.base import BaseTool, ToolRecoveryPolicy
from engine.tools.runtime.result import ToolResult


@dataclass(frozen=True)
class ToolExecutionControl:
    deadline: float
    cancelled: threading.Event

    def is_cancelled(self) -> bool:
        return self.cancelled.is_set() or time.monotonic() >= self.deadline


ToolOperation = Callable[[ToolExecutionControl], ToolResult]
TResult = TypeVar("TResult")


@dataclass(frozen=True)
class ToolExecutionTask(Generic[TResult]):
    operation: Callable[[], TResult]


class ToolExecutor:
    """Execute a frozen tool contract with timeout, retry and cancellation.

    Operations run on executor-owned threads and must create their database
    Session inside that thread. On timeout/cancel the control is signalled
    before the caller settles the durable ToolInvocation, so a late operation
    must roll back instead of publishing a successful result.
    """

    def __init__(
        self,
        *,
        max_workers: int = 4,
        poll_interval_seconds: float = 0.05,
        max_abandoned_workers: int = 8,
    ) -> None:
        self._max_workers = max(1, max_workers)
        self._max_abandoned_workers = max(1, max_abandoned_workers)
        self._poll_interval = max(0.01, poll_interval_seconds)
        self._pool_guard = threading.RLock()
        self._pool_generation = 0
        self._pool = self._new_pool()
        self._future_pools: dict[Future[ToolResult], ThreadPoolExecutor] = {}
        self._pool_futures: dict[ThreadPoolExecutor, set[Future[ToolResult]]] = {
            self._pool: set()
        }
        self._retired_pools: set[ThreadPoolExecutor] = set()
        self._abandoned_futures: set[Future[ToolResult]] = set()
        self._closed = False
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
        deadline: float | None = None,
    ) -> ToolResult:
        spec = tool.execution
        if spec.backend not in {"in_process", "isolated_process"}:
            return ToolResult(
                name=tool.name,
                status="failed",
                error=f"Tool execution backend '{spec.backend}' is unavailable.",
                error_code="TOOL_EXECUTION_BACKEND_UNAVAILABLE",
                latency_ms=0,
            )
        attempts = 0
        started = time.monotonic()

        while True:
            now = time.monotonic()
            remaining = (
                float(spec.timeout_seconds)
                if deadline is None
                else deadline - now
            )
            if remaining <= 0:
                return ToolResult(
                    name=tool.name,
                    status="failed",
                    error="Tool execution exceeded its deadline.",
                    error_code="TOOL_TIMEOUT",
                    latency_ms=int((now - started) * 1_000),
                    attempts=attempts,
                )
            timeout = min(float(spec.timeout_seconds), remaining)
            attempts += 1
            if on_attempt:
                on_attempt(attempts)
            cancelled = threading.Event()
            control = ToolExecutionControl(
                deadline=time.monotonic() + timeout,
                cancelled=cancelled,
            )
            future = self._submit(tool, scope_key, operation, control)
            if future is None:
                return ToolResult(
                    name=tool.name,
                    status="failed",
                    error="Tool execution capacity is temporarily unavailable.",
                    error_code="TOOL_EXECUTOR_SATURATED",
                    latency_ms=int((time.monotonic() - started) * 1_000),
                    attempts=attempts,
                )
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
                spec.recovery is ToolRecoveryPolicy.RETRY_SAFE
                and spec.retryable
                and attempts <= spec.max_retries
                and result.error_code not in {"TOOL_CANCELLED", "TOOL_TIMEOUT"}
            )
            if not can_retry:
                return result.model_copy(update={"attempts": attempts})

    def execute_batch(
        self,
        *,
        tasks: Sequence[ToolExecutionTask[TResult]],
        max_parallel: int | None = None,
    ) -> list[TResult]:
        """Execute callables in bounded parallel while preserving input order."""
        if not tasks:
            return []
        if self._closed:
            raise RuntimeError("Tool executor is no longer accepting work.")
        max_workers = max(
            1,
            min(
                len(tasks),
                max_parallel if max_parallel is not None else self._max_workers,
            ),
        )
        if max_workers > self._max_workers:
            max_workers = self._max_workers
        gate = threading.Semaphore(max_workers)

        def run_task(operation: Callable[[], TResult]) -> TResult:
            with gate:
                return operation()

        futures: list[Future[TResult]] = []
        for task in tasks:
            future = self._submit_batch_task(lambda op=task.operation: run_task(op))
            if future is None:
                for completed in futures:
                    try:
                        completed.result(timeout=0.001)
                    except Exception:
                        pass
                raise RuntimeError(
                    "Tool execution capacity is temporarily unavailable."
                )
            futures.append(future)
        return [future.result() for future in futures]

    def _submit(
        self,
        tool: BaseTool,
        scope_key: str,
        operation: ToolOperation,
        control: ToolExecutionControl,
    ) -> Future[ToolResult] | None:
        lock = self._scope_lock(scope_key) if tool.execution.concurrency == "sequential" else None

        def invoke() -> ToolResult:
            if lock is None:
                return operation(control)
            with lock:
                return operation(control)

        with self._pool_guard:
            if self._closed:
                return None
            if len(self._abandoned_futures) >= self._max_abandoned_workers:
                return None
            pool = self._pool
            future = pool.submit(invoke)
            self._future_pools[future] = pool
            self._pool_futures.setdefault(pool, set()).add(future)
            future.add_done_callback(self._future_finished)
            return future

    def _submit_batch_task(self, operation: Callable[[], TResult]) -> Future[TResult] | None:
        with self._pool_guard:
            if self._closed:
                return None
            if len(self._abandoned_futures) >= self._max_abandoned_workers:
                return None
            pool = self._pool
            future: Future[TResult] = pool.submit(operation)
            self._future_pools[future] = pool
            self._pool_futures.setdefault(pool, set()).add(future)
            future.add_done_callback(self._future_finished)
            return future

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

    def _stop(
        self,
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
        was_cancelled = future.cancel()
        if not was_cancelled and not future.done():
            self._quarantine_stuck_future(future)
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

    def _new_pool(self) -> ThreadPoolExecutor:
        self._pool_generation += 1
        return ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix=f"dbfox-tool-{self._pool_generation}",
        )

    def _quarantine_stuck_future(self, future: Future[ToolResult]) -> None:
        retired: ThreadPoolExecutor | None = None
        with self._pool_guard:
            owner = self._future_pools.get(future)
            if owner is None:
                return
            self._abandoned_futures.add(future)
            if owner is self._pool:
                retired = owner
                self._retired_pools.add(owner)
                self._pool = self._new_pool()
                self._pool_futures.setdefault(self._pool, set())
        if retired is not None:
            # Python cannot kill an already-running thread. Retire its whole pool
            # so later invocations receive fresh capacity; the cooperative
            # cancellation flag prevents a late result from committing.
            retired.shutdown(wait=False, cancel_futures=False)

    def _future_finished(self, future: Future[ToolResult]) -> None:
        retired_to_close: ThreadPoolExecutor | None = None
        with self._pool_guard:
            owner = self._future_pools.pop(future, None)
            self._abandoned_futures.discard(future)
            if owner is None:
                return
            futures = self._pool_futures.get(owner)
            if futures is not None:
                futures.discard(future)
                if not futures:
                    self._pool_futures.pop(owner, None)
                    if owner in self._retired_pools:
                        self._retired_pools.discard(owner)
                        retired_to_close = owner
        if retired_to_close is not None:
            retired_to_close.shutdown(wait=False, cancel_futures=False)

    def release_scope(self, scope_key: str) -> None:
        with self._locks_guard:
            self._locks.pop(scope_key, None)

    def close(self, *, wait: bool = False) -> None:
        with self._pool_guard:
            if self._closed:
                return
            self._closed = True
            pools = {self._pool, *self._retired_pools}
            self._retired_pools.clear()
        for pool in pools:
            pool.shutdown(wait=wait, cancel_futures=True)
        with self._locks_guard:
            self._locks.clear()

    @staticmethod
    def _enforce_output_limit(tool: BaseTool, result: ToolResult, attempts: int) -> ToolResult:
        if byte_size(result.output or {}) <= tool.execution.max_output_bytes:
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
