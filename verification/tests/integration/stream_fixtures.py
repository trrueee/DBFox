"""Provider-neutral streaming fixtures shared by opt-in Agent harnesses."""

from __future__ import annotations

import json

from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination


def tool_turn(call_id: str, name: str, arguments: dict[str, object]):
    encoded = json.dumps(arguments, ensure_ascii=False)
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id="tool:0",
        revision=1,
        tool_call_index=0,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id="tool:0",
        revision=2,
        tool_call_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="tool:0",
        revision=3,
        output_index=0,
        model_output_item={
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": encoded,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


def final_turn(content: str):
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
        content=content,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_END,
        item_id="answer",
        revision=3,
        output_index=0,
        message_status="completed",
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="answer",
        revision=4,
        output_index=0,
        model_output_item={
            "type": "message",
            "role": "assistant",
            "content": content,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )
