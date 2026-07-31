"""Bounded tool results supplied to the next Agent Turn."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.json_codec import canonical_dumps


class ObservationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
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
    model_output: str
    structured_result_ref: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    contributes_progress: bool = True
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    sequence: int = Field(ge=1)


def serialize_model_observation(
    *,
    status: str,
    summary: str,
    facts: dict[str, Any],
    artifact_ids: list[str],
    retryable: bool,
    error_code: str | None = None,
    error_message: str | None = None,
) -> str:
    """Build the single canonical function result shown to the model."""

    value: dict[str, Any] = {
        "status": status,
        "summary": summary,
        "facts": facts,
        "artifact_ids": artifact_ids,
        "retryable": retryable,
    }
    if error_code:
        value["error_code"] = error_code
    if error_message:
        value["error_message"] = error_message
    return canonical_dumps(value)
