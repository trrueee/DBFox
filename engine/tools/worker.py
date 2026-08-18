"""DBFox isolated tool worker entry point.

The parent starts this module as ``python -m engine.tools.worker``. It reads
one protocol handshake frame and one request frame from stdin, resolves only
the authorized resource scopes encoded in that request, runs the shared
``ToolAttemptHandler``, and writes exactly one ready frame followed by one
result/error frame to stdout.
"""

from __future__ import annotations

import sys
import traceback
from engine.runtime_composition import (
    build_attempt_resource_resolver,
    build_product_tool_registry,
)
from engine.tools.runtime.attempt import ToolAttemptRequest
from engine.tools.runtime.handler import ToolAttemptHandler
from engine.tools.runtime.result import ToolResult
from engine.tools.runtime.worker_protocol import (
    PROTOCOL_VERSION,
    WorkerProtocolError,
    read_frame,
    write_error_frame,
    write_frame,
)
def _public_failure(request: ToolAttemptRequest, code: str = "TOOL_EXECUTION_FAILED") -> ToolResult:
    return ToolResult(
        name=request.tool_name,
        status="failed",
        input=dict(request.authorized_input),
        error="Tool execution failed.",
        error_code=code,
        latency_ms=0,
    )


def main(argv: list[str] | None = None) -> int:
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    try:
        handshake = read_frame(stdin)
    except WorkerProtocolError as exc:
        write_error_frame(stdout, "TOOL_WORKER_PROTOCOL_ERROR", str(exc))
        return 2

    if handshake.get("protocol_version") != PROTOCOL_VERSION:
        write_error_frame(
            stdout,
            "TOOL_WORKER_PROTOCOL_VERSION_MISMATCH",
            "Unsupported isolated worker protocol version.",
        )
        return 2
    if handshake.get("kind") != "handshake":
        write_error_frame(
            stdout,
            "TOOL_WORKER_PROTOCOL_ERROR",
            "First worker frame must be a handshake.",
        )
        return 2

    try:
        write_frame(
            stdout,
            {"protocol_version": PROTOCOL_VERSION, "kind": "ready"},
        )
        request_frame = read_frame(stdin)
    except WorkerProtocolError as exc:
        write_error_frame(stdout, "TOOL_WORKER_PROTOCOL_ERROR", str(exc))
        return 2

    if request_frame.get("kind") != "request":
        write_error_frame(
            stdout,
            "TOOL_WORKER_PROTOCOL_ERROR",
            "Second worker frame must be a request.",
        )
        return 2
    if request_frame.get("protocol_version") != PROTOCOL_VERSION:
        write_error_frame(
            stdout,
            "TOOL_WORKER_PROTOCOL_VERSION_MISMATCH",
            "Unsupported isolated worker protocol version.",
        )
        return 2

    try:
        request = ToolAttemptRequest.model_validate(request_frame["request"])
    except Exception:
        write_error_frame(
            stdout,
            "TOOL_WORKER_INVALID_REQUEST",
            "Isolated worker request did not match its contract.",
        )
        return 2

    try:
        handler = ToolAttemptHandler(
            registry=build_product_tool_registry(),
            resolver=build_attempt_resource_resolver(),
        )
        result = handler.run(request)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        result = _public_failure(request)

    try:
        write_frame(
            stdout,
            {
                "protocol_version": PROTOCOL_VERSION,
                "kind": "result",
                "result": result.model_dump(mode="json"),
            },
        )
    except Exception:
        write_error_frame(
            stdout,
            "TOOL_WORKER_ENCODE_FAILED",
            "Isolated worker could not encode its result.",
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
