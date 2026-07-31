"""Provider-neutral Turn streaming and deterministic tool-call assembly."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.json_codec import JsonCodecError, loads


class TurnStreamKind(StrEnum):
    ANSWER_START = "answer_start"
    ANSWER_DELTA = "answer_delta"
    ANSWER_END = "answer_end"
    REASONING_SUMMARY_START = "reasoning_summary_start"
    REASONING_SUMMARY_DELTA = "reasoning_summary_delta"
    REASONING_SUMMARY_END = "reasoning_summary_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    MODEL_OUTPUT_ITEM = "model_output_item"
    USAGE = "usage"
    FINISH = "finish"
    ERROR = "error"


class TurnStreamItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TurnStreamKind
    item_id: str
    revision: int = Field(ge=1)
    content: str | None = None
    phase: Literal["commentary", "final_answer"] | None = None
    tool_call_index: int | None = Field(default=None, ge=0)
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_delta: str | None = None
    output_index: int | None = Field(default=None, ge=0)
    model_output_item: dict[str, Any] | None = None
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
    message_phase: Literal["commentary", "final_answer"] | None = None
    reasoning_summary: str = ""
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    output_items: list[dict[str, Any]] = Field(default_factory=list)
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
        expected_revisions: dict[str, int] = {}
        started: set[str] = set()
        ended: set[str] = set()
        tool_parts: dict[int, dict[str, str]] = {}
        output_items: dict[int, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        finish_signal: str | None = None
        message_phase: Literal["commentary", "final_answer"] | None = None

        for item in items:
            if item.phase is not None:
                message_phase = item.phase
            expected = expected_revisions.get(item.item_id, 0) + 1
            if item.revision < expected:
                continue
            if item.revision > expected:
                raise TurnStreamError(
                    f"Turn stream gap on {item.item_id}: expected {expected}, got {item.revision}"
                )
            expected_revisions[item.item_id] = item.revision

            if item.kind is TurnStreamKind.ERROR:
                raise TurnStreamError(item.error_message or item.error_code or "Provider stream failed")
            if item.kind in {
                TurnStreamKind.ANSWER_START,
                TurnStreamKind.REASONING_SUMMARY_START,
                TurnStreamKind.TOOL_CALL_START,
            }:
                if item.item_id in started:
                    raise TurnStreamError(f"Turn stream item started twice: {item.item_id}")
                started.add(item.item_id)
            elif item.kind in {
                TurnStreamKind.ANSWER_END,
                TurnStreamKind.REASONING_SUMMARY_END,
                TurnStreamKind.TOOL_CALL_END,
            }:
                if item.item_id not in started:
                    raise TurnStreamError(f"Turn stream item ended before start: {item.item_id}")
                ended.add(item.item_id)
            if item.kind is TurnStreamKind.ANSWER_DELTA:
                if item.item_id not in started or item.item_id in ended:
                    raise TurnStreamError("Answer delta is outside its item lifecycle")
                text_parts.append(item.content or "")
            elif item.kind is TurnStreamKind.REASONING_SUMMARY_DELTA:
                if item.item_id not in started or item.item_id in ended:
                    raise TurnStreamError("Reasoning summary delta is outside its item lifecycle")
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
                    if not current["name"]:
                        current["name"] = item.tool_name
                if item.arguments_delta:
                    current["arguments"] += item.arguments_delta
            elif item.kind is TurnStreamKind.MODEL_OUTPUT_ITEM:
                if item.output_index is None or item.model_output_item is None:
                    raise TurnStreamError(
                        "Completed model output item is missing its index or payload"
                    )
                previous = output_items.get(item.output_index)
                if previous is not None and previous != item.model_output_item:
                    raise TurnStreamError(
                        f"Model output index {item.output_index} completed twice"
                    )
                output_items[item.output_index] = item.model_output_item
            elif item.kind is TurnStreamKind.USAGE:
                for key, value in (item.usage or {}).items():
                    usage[key] = int(value)
            elif item.kind is TurnStreamKind.FINISH:
                finish_signal = item.finish_signal

        unclosed = started - ended
        if unclosed:
            raise TurnStreamError(
                f"Turn stream ended with incomplete items: {', '.join(sorted(unclosed))}"
            )

        tool_calls: list[ModelToolCall] = []
        for index in sorted(tool_parts):
            part = tool_parts[index]
            if not part["id"] or not part["name"]:
                raise TurnStreamError(f"Tool call {index} is incomplete")
            try:
                arguments = loads(part["arguments"] or "{}")
            except JsonCodecError as exc:
                raise TurnStreamError(f"Tool call {index} has invalid JSON arguments") from exc
            if not isinstance(arguments, dict):
                raise TurnStreamError(f"Tool call {index} arguments must be an object")
            tool_calls.append(
                ModelToolCall(id=part["id"], name=part["name"], arguments=arguments)
            )
        output_call_ids = {
            str(item.get("call_id") or "")
            for item in output_items.values()
            if item.get("type") == "function_call"
        }
        missing_output_items = [
            call.id for call in tool_calls if call.id not in output_call_ids
        ]
        if missing_output_items:
            raise TurnStreamError(
                "Tool calls are missing their completed model output Items: "
                + ", ".join(missing_output_items)
            )

        return ModelTurnResult(
            text="".join(text_parts),
            message_phase=message_phase,
            reasoning_summary="".join(reasoning_parts),
            tool_calls=tool_calls,
            output_items=[output_items[index] for index in sorted(output_items)],
            usage=usage,
            finish_signal=finish_signal,
        )
