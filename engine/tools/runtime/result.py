"""Provider-neutral result returned by a tool leaf."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["success", "failed"]
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    latency_ms: int
    attempts: int = 1
