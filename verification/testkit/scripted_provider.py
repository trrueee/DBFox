"""Capability-neutral scripted Responses events for Core verification."""

from __future__ import annotations

import json
from typing import Any, Iterable

from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination


def answer_events(text: str) -> Iterable[TurnStreamItem]:
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_START,
        item_id="answer",
        revision=1,
        output_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_DELTA,
        item_id="answer",
        revision=2,
        output_index=0,
        content=text,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_END,
        item_id="answer",
        revision=3,
        output_index=0,
        phase="final_answer",
        message_status="completed",
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="answer",
        revision=4,
        output_index=0,
        model_output_item={"type": "message", "role": "assistant", "content": text},
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


def tool_call_events(
    *,
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> Iterable[TurnStreamItem]:
    encoded = json.dumps(arguments, separators=(",", ":"))
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id=f"tool:{call_id}",
        revision=1,
        tool_call_index=0,
        tool_call_id=call_id,
        tool_name=tool_name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id=f"tool:{call_id}",
        revision=2,
        tool_call_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id=f"tool:{call_id}",
        revision=3,
        output_index=0,
        model_output_item={
            "type": "function_call",
            "call_id": call_id,
            "name": tool_name,
            "arguments": encoded,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


class ScriptedProvider:
    def __init__(self, events: Iterable[TurnStreamItem]) -> None:
        self._events = tuple(events)

    def stream(self, **_kwargs: Any) -> Iterable[TurnStreamItem]:
        yield from self._events
