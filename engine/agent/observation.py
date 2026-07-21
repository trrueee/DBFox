"""Bounded tool results supplied to the next Agent Turn."""

from __future__ import annotations

from enum import StrEnum
import json
from threading import Lock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObservationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    turn_id: str
    tool_invocation_id: str
    tool_name: str
    tool_version: str
    status: ObservationStatus
    model_visible_summary: str
    structured_result_ref: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    sequence: int = Field(ge=1)


class TransientObservationBuffer:
    """One-shot model-visible tool results that never enter durable Agent state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._by_run: dict[str, list[dict[str, Any]]] = {}

    def publish(
        self,
        *,
        run_id: str,
        tool_name: str,
        artifact_ids: list[str],
        output: dict[str, Any],
    ) -> None:
        value = {
            "toolName": tool_name,
            "artifactIds": list(artifact_ids),
            "result": _bounded_transient_result(output),
        }
        with self._lock:
            self._by_run.setdefault(run_id, []).append(value)

    def consume(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._by_run.pop(run_id, [])

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._by_run.pop(run_id, None)


def _bounded_transient_result(output: dict[str, Any]) -> dict[str, Any]:
    value = dict(output)
    for key, limit in (("rows", 50), ("results", 50), ("series", 100)):
        if isinstance(value.get(key), list):
            value[key] = value[key][:limit]
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) <= 32_768:
        return value
    return {"truncated": True, "content": encoded[:16_000]}
