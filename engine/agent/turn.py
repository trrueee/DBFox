"""Provider-neutral Turn streaming and deterministic tool-call assembly."""

from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TurnStreamKind(StrEnum):
    TEXT_DELTA = "text_delta"
    REASONING_SUMMARY_DELTA = "reasoning_summary_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    USAGE = "usage"
    FINISH = "finish"
    ERROR = "error"


class TurnStreamItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TurnStreamKind
    channel: str
    offset: int = Field(ge=0)
    content: str | None = None
    tool_call_index: int | None = Field(default=None, ge=0)
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_delta: str | None = None
    usage: dict[str, int] | None = None
    finish_signal: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    arguments: dict[str, Any]


class ModelTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = ""
    reasoning_summary: str = ""
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    finish_signal: str | None = None


class TurnStreamError(RuntimeError):
    pass


class TurnStreamCancelled(TurnStreamError):
    pass


class TurnStreamAssembler:
    """Merge normalized provider items without provider-specific types."""

    def consume(self, items: Iterable[TurnStreamItem]) -> ModelTurnResult:
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        expected_offsets: dict[str, int] = {}
        tool_parts: dict[int, dict[str, str]] = {}
        usage: dict[str, int] = {}
        finish_signal: str | None = None

        for item in items:
            expected = expected_offsets.get(item.channel, 0)
            if item.offset < expected:
                continue
            if item.offset > expected:
                raise TurnStreamError(
                    f"Turn stream gap on {item.channel}: expected {expected}, got {item.offset}"
                )
            expected_offsets[item.channel] = expected + 1

            if item.kind is TurnStreamKind.ERROR:
                raise TurnStreamError(item.error_message or item.error_code or "Provider stream failed")
            if item.kind is TurnStreamKind.TEXT_DELTA:
                text_parts.append(item.content or "")
            elif item.kind is TurnStreamKind.REASONING_SUMMARY_DELTA:
                reasoning_parts.append(item.content or "")
            elif item.kind in {
                TurnStreamKind.TOOL_CALL_START,
                TurnStreamKind.TOOL_CALL_DELTA,
                TurnStreamKind.TOOL_CALL_END,
            }:
                if item.tool_call_index is None:
                    raise TurnStreamError("Tool-call stream item is missing its index")
                current = tool_parts.setdefault(
                    item.tool_call_index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if item.tool_call_id:
                    current["id"] = item.tool_call_id
                if item.tool_name:
                    current["name"] += item.tool_name
                if item.arguments_delta:
                    current["arguments"] += item.arguments_delta
            elif item.kind is TurnStreamKind.USAGE:
                for key, value in (item.usage or {}).items():
                    usage[key] = int(value)
            elif item.kind is TurnStreamKind.FINISH:
                finish_signal = item.finish_signal

        tool_calls: list[ModelToolCall] = []
        for index in sorted(tool_parts):
            part = tool_parts[index]
            if not part["id"] or not part["name"]:
                raise TurnStreamError(f"Tool call {index} is incomplete")
            try:
                arguments = json.loads(part["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                raise TurnStreamError(f"Tool call {index} has invalid JSON arguments") from exc
            if not isinstance(arguments, dict):
                raise TurnStreamError(f"Tool call {index} arguments must be an object")
            tool_calls.append(
                ModelToolCall(id=part["id"], name=part["name"], arguments=arguments)
            )

        return ModelTurnResult(
            text="".join(text_parts),
            reasoning_summary="".join(reasoning_parts),
            tool_calls=tool_calls,
            usage=usage,
            finish_signal=finish_signal,
        )
