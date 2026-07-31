from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openai.types.responses import ResponseStreamEvent
from pydantic import TypeAdapter

from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.turn import (
    TurnStreamAssembler,
    TurnStreamCancelled,
    TurnStreamError,
    TurnStreamKind,
)

_STREAM_EVENT = TypeAdapter(ResponseStreamEvent)


def _event(payload: dict[str, Any]) -> ResponseStreamEvent:
    """Build the exact SDK model delivered by an OpenAI Responses stream."""

    return _STREAM_EVENT.validate_python(payload)


def _message(
    item_id: str,
    *,
    phase: str,
    status: str,
    text: str = "",
    refusal: str = "",
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if text:
        content.append({
            "type": "output_text",
            "text": text,
            "annotations": [],
            "logprobs": [],
        })
    if refusal:
        content.append({"type": "refusal", "refusal": refusal})
    return {
        "id": item_id,
        "type": "message",
        "role": "assistant",
        "status": status,
        "phase": phase,
        "content": content,
    }


def _function_call(
    item_id: str,
    *,
    call_id: str,
    name: str,
    arguments: str,
    status: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": status,
    }


def _response(
    *,
    status: str,
    output: list[dict[str, Any]] | None = None,
    usage: dict[str, Any] | None = None,
    incomplete_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "created_at": 0,
        "model": "gpt-5",
        "object": "response",
        "output": output or [],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "status": status,
        "usage": usage,
        "incomplete_details": incomplete_details,
    }


class _EventStream:
    def __init__(self, events: list[ResponseStreamEvent]) -> None:
        self._events = iter(events)
        self.closed = False

    def __iter__(self) -> "_EventStream":
        return self

    def __next__(self) -> ResponseStreamEvent:
        return next(self._events)

    def close(self) -> None:
        self.closed = True


class _Responses:
    def __init__(self, events: list[ResponseStreamEvent]) -> None:
        self.events = events
        self.stream: _EventStream | None = None
        self.request: dict[str, object] | None = None

    def create(self, **request: object) -> _EventStream:
        self.request = request
        self.stream = _EventStream(self.events)
        return self.stream


class _Client:
    def __init__(self, events: list[ResponseStreamEvent]) -> None:
        self.responses = _Responses(events)


def test_responses_adapter_preserves_phase_calls_outputs_and_usage() -> None:
    completed_message = _message(
        "msg_1",
        phase="commentary",
        status="completed",
        text="我先检查订单结构。",
    )
    completed_call = _function_call(
        "fc_1",
        call_id="call_1",
        name="schema_inspect",
        arguments='{"table_name":"orders"}',
        status="completed",
    )
    reasoning_item = {
        "id": "reasoning_1",
        "type": "reasoning",
        "encrypted_content": "opaque-reasoning-state",
        "summary": [],
        "status": "completed",
    }
    client = _Client([
        _event({
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": _message(
                "msg_1",
                phase="commentary",
                status="in_progress",
            ),
        }),
        _event({
            "type": "response.output_text.delta",
            "sequence_number": 2,
            "item_id": "msg_1",
            "output_index": 0,
            "content_index": 0,
            "delta": "我先检查订单结构。",
            "logprobs": [],
        }),
        _event({
            "type": "response.output_item.done",
            "sequence_number": 3,
            "output_index": 0,
            "item": completed_message,
        }),
        _event({
            "type": "response.output_item.added",
            "sequence_number": 4,
            "output_index": 1,
            "item": _function_call(
                "fc_1",
                call_id="call_1",
                name="schema_inspect",
                arguments="",
                status="in_progress",
            ),
        }),
        _event({
            "type": "response.function_call_arguments.delta",
            "sequence_number": 5,
            "item_id": "fc_1",
            "output_index": 1,
            "delta": '{"table_name":"ord',
        }),
        _event({
            "type": "response.function_call_arguments.delta",
            "sequence_number": 6,
            "item_id": "fc_1",
            "output_index": 1,
            "delta": 'ers"}',
        }),
        _event({
            "type": "response.output_item.done",
            "sequence_number": 7,
            "output_index": 1,
            "item": completed_call,
        }),
        _event({
            "type": "response.reasoning_summary_text.delta",
            "sequence_number": 8,
            "item_id": "reasoning_1",
            "output_index": 2,
            "summary_index": 0,
            "delta": "正在确认所需数据。",
        }),
        _event({
            "type": "response.output_item.done",
            "sequence_number": 9,
            "output_index": 2,
            "item": reasoning_item,
        }),
        _event({
            "type": "response.completed",
            "sequence_number": 10,
            "response": _response(
                status="completed",
                output=[completed_message, completed_call, reasoning_item],
                usage={
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 4,
                    "output_tokens_details": {"reasoning_tokens": 1},
                    "total_tokens": 14,
                },
            ),
        }),
    ])
    adapter = OpenAIModelAdapter(client=client, model_name="gpt-5")  # type: ignore[arg-type]
    input_items = [
        {"role": "user", "content": "查一下"},
        {
            "type": "function_call_output",
            "call_id": "prior_call",
            "output": "先前结果",
        },
    ]
    tools = [{
        "type": "function",
        "name": "schema_inspect",
        "description": "读取表结构",
        "parameters": {"type": "object", "properties": {}},
    }]

    result = TurnStreamAssembler().consume(
        adapter.stream(messages=input_items, tools=tools)
    )

    assert result.text == "我先检查订单结构。"
    assert result.message_phase == "commentary"
    assert result.reasoning_summary == "正在确认所需数据。"
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "schema_inspect"
    assert result.tool_calls[0].arguments == {"table_name": "orders"}
    assert [item["type"] for item in result.output_items] == [
        "message",
        "function_call",
        "reasoning",
    ]
    assert result.output_items[0]["phase"] == "commentary"
    assert result.output_items[1]["call_id"] == "call_1"
    assert result.output_items[2]["encrypted_content"] == "opaque-reasoning-state"
    assert result.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    assert client.responses.request == {
        "model": "gpt-5",
        "input": input_items,
        "stream": True,
        "store": False,
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }


def test_responses_adapter_preserves_final_answer_phase_and_bounds_deltas() -> None:
    content = "数" * 205
    completed = _message(
        "msg_final",
        phase="final_answer",
        status="completed",
        text=content,
    )
    client = _Client([
        _event({
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": _message(
                "msg_final",
                phase="final_answer",
                status="in_progress",
            ),
        }),
        _event({
            "type": "response.output_text.delta",
            "sequence_number": 2,
            "item_id": "msg_final",
            "output_index": 0,
            "content_index": 0,
            "delta": content,
            "logprobs": [],
        }),
        _event({
            "type": "response.output_item.done",
            "sequence_number": 3,
            "output_index": 0,
            "item": completed,
        }),
        _event({
            "type": "response.completed",
            "sequence_number": 4,
            "response": _response(status="completed", output=[completed]),
        }),
    ])

    items = list(OpenAIModelAdapter(
        client=client,  # type: ignore[arg-type]
        model_name="gpt-5",
    ).stream(messages=[], tools=[]))

    deltas = [item for item in items if item.kind is TurnStreamKind.ANSWER_DELTA]
    assert [len(item.content or "") for item in deltas] == [96, 96, 13]
    result = TurnStreamAssembler().consume(items)
    assert result.text == content
    assert result.message_phase == "final_answer"


def test_responses_adapter_preserves_refusal_text() -> None:
    refusal = "我不能执行这个请求。"
    completed = _message(
        "msg_refusal",
        phase="final_answer",
        status="completed",
        refusal=refusal,
    )
    client = _Client([
        _event({
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": _message(
                "msg_refusal",
                phase="final_answer",
                status="in_progress",
            ),
        }),
        _event({
            "type": "response.refusal.delta",
            "sequence_number": 2,
            "item_id": "msg_refusal",
            "output_index": 0,
            "content_index": 0,
            "delta": refusal,
        }),
        _event({
            "type": "response.refusal.done",
            "sequence_number": 3,
            "item_id": "msg_refusal",
            "output_index": 0,
            "content_index": 0,
            "refusal": refusal,
        }),
        _event({
            "type": "response.output_item.done",
            "sequence_number": 4,
            "output_index": 0,
            "item": completed,
        }),
        _event({
            "type": "response.completed",
            "sequence_number": 5,
            "response": _response(status="completed", output=[completed]),
        }),
    ])

    result = TurnStreamAssembler().consume(
        OpenAIModelAdapter(
            client=client,  # type: ignore[arg-type]
            model_name="gpt-5",
        ).stream(messages=[], tools=[])
    )

    assert result.text == refusal
    assert result.message_phase == "final_answer"


def test_responses_adapter_uses_completed_message_when_no_text_delta_arrives() -> None:
    completed = _message(
        "msg_final",
        phase="final_answer",
        status="completed",
        text="最终答案",
    )
    client = _Client([
        _event({
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": _message(
                "msg_final",
                phase="final_answer",
                status="in_progress",
            ),
        }),
        _event({
            "type": "response.output_item.done",
            "sequence_number": 2,
            "output_index": 0,
            "item": completed,
        }),
        _event({
            "type": "response.completed",
            "sequence_number": 3,
            "response": _response(status="completed", output=[completed]),
        }),
    ])

    result = TurnStreamAssembler().consume(
        OpenAIModelAdapter(
            client=client,  # type: ignore[arg-type]
            model_name="gpt-5",
        ).stream(messages=[], tools=[])
    )

    assert result.text == "最终答案"
    assert result.message_phase == "final_answer"


def test_responses_adapter_rejects_terminal_incomplete_response() -> None:
    client = _Client([
        _event({
            "type": "response.incomplete",
            "sequence_number": 1,
            "response": _response(
                status="incomplete",
                incomplete_details={"reason": "max_output_tokens"},
            ),
        }),
    ])

    with pytest.raises(
        TurnStreamError,
        match=r"Model response was incomplete \(max_output_tokens\)",
    ):
        TurnStreamAssembler().consume(
            OpenAIModelAdapter(
                client=client,  # type: ignore[arg-type]
                model_name="gpt-5",
            ).stream(messages=[{"role": "user", "content": "test"}], tools=[])
        )


def test_responses_adapter_rejects_stream_without_terminal_event() -> None:
    client = _Client([
        _event({
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": _message(
                "msg_partial",
                phase="final_answer",
                status="in_progress",
            ),
        }),
        _event({
            "type": "response.output_text.delta",
            "sequence_number": 2,
            "item_id": "msg_partial",
            "output_index": 0,
            "content_index": 0,
            "delta": "partial",
            "logprobs": [],
        }),
    ])

    with pytest.raises(
        TurnStreamError,
        match="without a terminal response event",
    ):
        TurnStreamAssembler().consume(
            OpenAIModelAdapter(
                client=client,  # type: ignore[arg-type]
                model_name="gpt-5",
            ).stream(messages=[{"role": "user", "content": "test"}], tools=[])
        )


def test_responses_adapter_emits_safe_error_item() -> None:
    class _FailingResponses:
        def create(self, **_request: object) -> object:
            raise RuntimeError("secret provider detail")

    client = SimpleNamespace(responses=_FailingResponses())
    item = list(OpenAIModelAdapter(
        client=client,  # type: ignore[arg-type]
        model_name="gpt-5",
    ).stream(messages=[], tools=[]))[0]

    assert item.kind is TurnStreamKind.ERROR
    assert item.error_code == "MODEL_PROVIDER_STREAM_FAILED"
    assert "secret provider detail" not in (item.error_message or "")


def test_responses_stream_honors_cancellation_and_closes_sdk_stream() -> None:
    client = _Client([
        _event({
            "type": "response.output_item.added",
            "sequence_number": 1,
            "output_index": 0,
            "item": _message(
                "msg_1",
                phase="final_answer",
                status="in_progress",
            ),
        }),
    ])
    adapter = OpenAIModelAdapter(
        client=client,  # type: ignore[arg-type]
        model_name="gpt-5",
    )

    with pytest.raises(TurnStreamCancelled, match="cancelled"):
        list(adapter.stream(messages=[], tools=[], cancellation_probe=lambda: True))

    assert client.responses.stream is not None
    assert client.responses.stream.closed
