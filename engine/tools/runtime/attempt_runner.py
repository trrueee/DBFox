"""Attempt transport seam.

ToolExecutor remains the only owner of retry/deadline/recovery. A runner only
moves one serializable ToolAttemptRequest to a thread or worker process.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Protocol

from engine.json_codec import loads
from engine.tools.runtime.attempt import ToolAttemptRequest
from engine.tools.runtime.result import ToolResult
from engine.tools.runtime.worker_protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    encode_frame,
)

_DEFAULT_MAX_STDOUT_BYTES = MAX_FRAME_BYTES * 2
_DEFAULT_MAX_STDERR_BYTES = 64 * 1024


def default_isolated_worker_command() -> tuple[str, ...]:
    """Return the development worker command.

    Frozen Sidecar packaging may need to replace this with a real sidecar-local
    command before ``isolated_process`` is enabled in production.
    """

    return (sys.executable, "-m", "engine.tools.worker")


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
            return _result(
                request,
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
    """Run one attempt in a subprocess using the DBFox worker protocol."""

    protocol_version = PROTOCOL_VERSION

    def __init__(
        self,
        worker_command: tuple[str, ...] | None = None,
        *,
        max_stdout_bytes: int = _DEFAULT_MAX_STDOUT_BYTES,
        max_stderr_bytes: int = _DEFAULT_MAX_STDERR_BYTES,
        poll_interval_seconds: float = 0.01,
    ) -> None:
        command = tuple(worker_command or default_isolated_worker_command())
        if not command:
            raise ValueError("isolated worker command must not be empty")
        self.worker_command = command
        self.max_stdout_bytes = max_stdout_bytes
        self.max_stderr_bytes = max_stderr_bytes
        self.poll_interval_seconds = max(0.001, poll_interval_seconds)

    def run(
        self,
        *,
        request: ToolAttemptRequest,
        control: ToolExecutionControlLike,
    ) -> ToolResult:
        started = time.monotonic()
        if control.is_cancelled():
            return _result(
                request,
                error="Tool execution was cancelled.",
                error_code="TOOL_CANCELLED",
                latency_ms=0,
            )
        deadline = min(
            control.deadline,
            started + (request.attempt_timeout_ms / 1_000),
        )
        if deadline <= started:
            return _result(
                request,
                error="Tool execution exceeded its deadline.",
                error_code="TOOL_TIMEOUT",
                latency_ms=0,
            )

        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        stdout_overflow = threading.Event()
        stderr_overflow = threading.Event()
        process = self._start_process()
        if process is None:
            return _result(
                request,
                error="Isolated worker backend is unavailable.",
                error_code="TOOL_EXECUTION_BACKEND_UNAVAILABLE",
                latency_ms=int((time.monotonic() - started) * 1_000),
            )

        stdout_thread = threading.Thread(
            target=_read_bounded_stream,
            args=(
                process.stdout,
                stdout_buffer,
                self.max_stdout_bytes,
                stdout_overflow,
            ),
            name="dbfox-worker-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_read_bounded_stream,
            args=(
                process.stderr,
                stderr_buffer,
                self.max_stderr_bytes,
                stderr_overflow,
            ),
            name="dbfox-worker-stderr",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        handshake = {"protocol_version": self.protocol_version, "kind": "handshake"}
        request_frame = {
            "protocol_version": self.protocol_version,
            "kind": "request",
            "request": request.model_dump(mode="json"),
        }
        try:
            payload = encode_frame(handshake) + b"\n" + encode_frame(request_frame) + b"\n"
            if process.stdin is not None:
                process.stdin.write(payload)
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass

        while True:
            if control.is_cancelled():
                _terminate_process_tree(process)
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                return _result(
                    request,
                    error="Tool execution was cancelled.",
                    error_code="TOOL_CANCELLED",
                    latency_ms=int((time.monotonic() - started) * 1_000),
                )
            if stdout_overflow.is_set() or stderr_overflow.is_set():
                _terminate_process_tree(process)
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                return _result(
                    request,
                    error="Isolated worker output exceeded its bounded limit.",
                    error_code="TOOL_EXECUTION_OUTPUT_TOO_LARGE",
                    latency_ms=int((time.monotonic() - started) * 1_000),
                )
            if process.poll() is not None:
                break
            if time.monotonic() >= deadline:
                _terminate_process_tree(process)
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                return _result(
                    request,
                    error="Tool execution exceeded its deadline.",
                    error_code="TOOL_TIMEOUT",
                    latency_ms=int((time.monotonic() - started) * 1_000),
                )
            time.sleep(self.poll_interval_seconds)

        # A late success after cancellation is never accepted.
        if control.is_cancelled():
            _terminate_process_tree(process)
            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)
            return _result(
                request,
                error="Tool execution was cancelled.",
                error_code="TOOL_CANCELLED",
                latency_ms=int((time.monotonic() - started) * 1_000),
            )

        process.wait(timeout=1.0)
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            return _result(
                request,
                error="Isolated worker output could not be collected.",
                error_code="TOOL_EXECUTION_INVALID_RESULT",
                latency_ms=int((time.monotonic() - started) * 1_000),
            )
        parsed = _parse_worker_output(request, bytes(stdout_buffer), started)
        if (
            parsed.error_code == "TOOL_EXECUTION_INVALID_RESULT"
            and process.returncode != 0
        ):
            return _result(
                request,
                error="The isolated worker outcome is unknown.",
                error_code="TOOL_OUTCOME_UNKNOWN",
                latency_ms=int((time.monotonic() - started) * 1_000),
            )
        return parsed

    def _start_process(self) -> subprocess.Popen[bytes] | None:
        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", None)
            if not isinstance(creationflags, int):
                # Do not start a Windows worker without the process group that
                # makes timeout/cancellation tree termination safe.
                return None
            kwargs["creationflags"] = creationflags
        else:
            kwargs["start_new_session"] = True
        try:
            return subprocess.Popen(self.worker_command, **kwargs)
        except OSError:
            return None


def _read_bounded_stream(
    stream: Any,
    sink: bytearray,
    limit: int,
    overflow: threading.Event,
) -> None:
    try:
        while not overflow.is_set():
            chunk = stream.readline(limit + 1)
            if not chunk:
                break
            if len(chunk) > limit or len(sink) + len(chunk) > limit:
                overflow.set()
                break
            sink.extend(chunk)
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            pass
    else:
        try:
            killpg = getattr(os, "killpg", None)
            getpgid = getattr(os, "getpgid", None)
            sigkill = getattr(signal, "SIGKILL", None)
            if callable(killpg) and callable(getpgid) and sigkill is not None:
                killpg(getpgid(process.pid), sigkill)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        process.kill()
    except OSError:
        pass


def _parse_worker_output(
    request: ToolAttemptRequest,
    output: bytes,
    started: float,
) -> ToolResult:
    lines = output.splitlines()
    if not lines:
        return _result(
            request,
            error="Isolated worker returned no result.",
            error_code="TOOL_EXECUTION_INVALID_RESULT",
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    first = _decode_line(lines[0])
    if first is not None and first.get("kind") == "error":
        return _result(
            request,
            error=str(first.get("error") or "Isolated worker failed."),
            error_code=str(first.get("error_code") or "TOOL_EXECUTION_FAILED"),
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    if len(lines) < 2:
        return _result(
            request,
            error="Isolated worker returned an incomplete response.",
            error_code="TOOL_EXECUTION_INVALID_RESULT",
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    ready = _decode_line(lines[0])
    response = _decode_line(lines[1])
    if (
        ready is None
        or ready.get("protocol_version") != PROTOCOL_VERSION
        or ready.get("kind") != "ready"
        or response is None
        or response.get("protocol_version") != PROTOCOL_VERSION
        or response.get("kind") not in {"result", "error"}
    ):
        return _result(
            request,
            error="Isolated worker returned a malformed response.",
            error_code="TOOL_EXECUTION_INVALID_RESULT",
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    if response.get("kind") == "error":
        return _result(
            request,
            error=str(response.get("error") or "Isolated worker failed."),
            error_code=str(response.get("error_code") or "TOOL_EXECUTION_FAILED"),
            latency_ms=int((time.monotonic() - started) * 1_000),
        )
    try:
        return ToolResult.model_validate(response["result"])
    except Exception:
        return _result(
            request,
            error="Isolated worker returned an invalid ToolResult.",
            error_code="TOOL_EXECUTION_INVALID_RESULT",
            latency_ms=int((time.monotonic() - started) * 1_000),
        )


def _decode_line(line: bytes) -> dict[str, Any] | None:
    try:
        value = loads(line.decode("utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _result(
    request: ToolAttemptRequest,
    *,
    error: str,
    error_code: str,
    latency_ms: int,
) -> ToolResult:
    return ToolResult(
        name=request.tool_name,
        status="failed",
        input=dict(request.authorized_input),
        error=error,
        error_code=error_code,
        latency_ms=latency_ms,
    )
