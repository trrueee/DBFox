"""Line-delimited JSON protocol for the DBFox isolated tool worker.

The protocol is intentionally tiny. A parent writes two newline-delimited
frames to the worker stdin: one ``handshake`` frame and one ``request`` frame.
The worker writes one ``ready`` frame followed by exactly one ``result`` or
``error`` frame to stdout. All other diagnostic output must go to stderr.

Frames are single-line UTF-8 JSON objects. A frame larger than
``MAX_FRAME_BYTES`` is a protocol violation. This keeps stdout unambiguous and
bounds the parent parser without introducing a length-prefix dependency.
"""

from __future__ import annotations

import sys
from typing import Any

from engine.json_codec import dumps, load_object

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 16 * 1024 * 1024


class WorkerProtocolError(ValueError):
    """The isolated worker exchange does not match the DBFox wire contract."""


def encode_frame(payload: dict[str, Any]) -> bytes:
    """Serialize one protocol frame without a trailing newline."""

    text = dumps(payload)
    raw = text.encode("utf-8")
    if len(raw) > MAX_FRAME_BYTES:
        raise WorkerProtocolError(
            f"Worker protocol frame exceeds {MAX_FRAME_BYTES} bytes"
        )
    return raw


def write_frame(stream: Any, payload: dict[str, Any]) -> None:
    """Write one newline-terminated frame to a binary stream."""

    stream.write(encode_frame(payload) + b"\n")
    stream.flush()


def read_frame(stream: Any, *, max_bytes: int = MAX_FRAME_BYTES) -> dict[str, Any]:
    """Read one newline-terminated JSON object from a binary stream."""

    line = stream.readline(max_bytes + 1)
    if not line:
        raise WorkerProtocolError("Worker stdin closed before a frame was received")
    if len(line) > max_bytes:
        raise WorkerProtocolError("Worker frame exceeds the maximum allowed size")
    if not line.endswith(b"\n"):
        raise WorkerProtocolError("Worker frame is missing a newline terminator")
    text = line.rstrip(b"\r\n").decode("utf-8")
    try:
        return load_object(text)
    except Exception as exc:
        raise WorkerProtocolError("Worker frame is not a JSON object") from exc


def write_error_frame(stream: Any, error_code: str, message: str) -> None:
    """Write a protocol-level error frame and flush it to stdout."""

    write_frame(
        stream,
        {
            "protocol_version": PROTOCOL_VERSION,
            "kind": "error",
            "error_code": error_code,
            "error": message,
        },
    )


def main_streams() -> tuple[Any, Any]:
    """Return stdin/stdout binary streams for a normal Python worker."""

    return sys.stdin.buffer, sys.stdout.buffer
