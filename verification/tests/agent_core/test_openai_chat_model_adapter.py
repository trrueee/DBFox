"""Chat Completions adapter: streaming translation and transcript conversion."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openai.types.chat import ChatCompletionChunk

from engine.agent.loop import ProviderSettings
from engine.agent.providers import (
    PROVIDER_CHAT,
    PROVIDER_RESPONSES,
    project_tool_schemas,
)
from engine.agent.providers.openai_chat import (
    OpenAIChatModelAdapter,
    to_chat_messages,
)
from engine.agent.turn import (
    TurnStreamAssembler,
    TurnStreamError,
    TurnTermination,
)
from engine.llm.config import LlmConfigurationError
from engine.models import AgentRun


class _AsyncChunks:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = iter(chunks)
        self.closed = False

    def __aiter__(self) -> "_AsyncChunks":
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def close(self) -> None:
        self.closed = True


class _FakeCompletions:
    def __init__(self, chunks: list[object]) -> None:
        self.chunks = chunks
        self.request: dict[str, Any] | None = None

    async def create(self, **request: Any) -> _AsyncChunks:
        self.request = request
        return _AsyncChunks(self.chunks)


def _client(chunks: list[object]) -> tuple[Any, _FakeCompletions]:
    completions = _FakeCompletions(chunks)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )
    return client, completions


def _delta_chunk(
    *,
    content: str | None = None,
    tool_calls: list[object] | None = None,
    finish_reason: str | None = None,
) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=tool_calls),
                finish_reason=finish_reason,
            )
        ],
        usage=None,
    )


def _usage_chunk(**usage: int) -> object:
    return SimpleNamespace(choices=[], usage=SimpleNamespace(**usage))


def _tool_delta(
    *,
    index: int,
    call_id: str | None,
    name: str | None,
    arguments: str | None,
) -> object:
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _stream(chunks: list[object]) -> Any:
    client, _ = _client(chunks)
    adapter = OpenAIChatModelAdapter(client=client, model_name="deepseek-chat")
    return adapter.stream(messages=[{"role": "user", "content": "hi"}], tools=[])


def test_chat_text_and_usage_are_normalized() -> None:
    chunks = [
        _delta_chunk(content="Hello"),
        _delta_chunk(content=" world"),
        _usage_chunk(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        _delta_chunk(finish_reason="stop"),
    ]

    result = TurnStreamAssembler().consume(_stream(chunks))

    assert result.termination is TurnTermination.COMPLETED
    assert result.display_text == "Hello world"
    assert result.usage["input_tokens"] == 10
    assert result.usage["output_tokens"] == 5
    assert result.tool_calls == []


def test_chat_tool_call_fragments_are_assembled_with_output_item() -> None:
    chunks = [
        _delta_chunk(
            tool_calls=[
                _tool_delta(
                    index=0,
                    call_id="call_a",
                    name="sql_validate",
                    arguments='{"sql":',
                )
            ]
        ),
        _delta_chunk(
            tool_calls=[
                _tool_delta(
                    index=0,
                    call_id=None,
                    name=None,
                    arguments='"SELECT 1"}',
                )
            ]
        ),
        _delta_chunk(finish_reason="tool_calls"),
    ]

    result = TurnStreamAssembler().consume(_stream(chunks))

    assert result.termination is TurnTermination.COMPLETED
    assert [call.id for call in result.tool_calls] == ["call_a"]
    assert result.tool_calls[0].name == "sql_validate"
    assert result.tool_calls[0].arguments == {"sql": "SELECT 1"}
    assert result.output_items[0]["type"] == "function_call"
    assert result.output_items[0]["call_id"] == "call_a"


def test_chat_length_finish_is_an_incomplete_provider_response() -> None:
    chunks = [
        _delta_chunk(content="partial"),
        _delta_chunk(finish_reason="length"),
    ]

    with pytest.raises(TurnStreamError) as raised:
        TurnStreamAssembler().consume(_stream(chunks))

    assert raised.value.code == "MODEL_PROVIDER_INCOMPLETE"


def test_chat_tool_call_without_a_name_fails_closed() -> None:
    chunks = [
        _delta_chunk(
            tool_calls=[
                _tool_delta(index=0, call_id="call_a", name=None, arguments="{}")
            ]
        ),
        _delta_chunk(finish_reason="tool_calls"),
    ]

    with pytest.raises(TurnStreamError) as raised:
        TurnStreamAssembler().consume(_stream(chunks))

    assert raised.value.code == "MODEL_PROVIDER_PROTOCOL_ERROR"


def test_chat_thinking_remains_private_and_round_trips_with_the_tool_output() -> None:
    chunks = [ChatCompletionChunk.model_validate({
        "id": "chat-result", "object": "chat.completion.chunk", "created": 1,
        "model": "deepseek-reasoner", "choices": [{
            "index": 0, "finish_reason": None,
            "delta": {"reasoning_content": "opaque continuation"},
        }],
    }), _delta_chunk(content="I'll check."), _delta_chunk(
        tool_calls=[_tool_delta(index=0, call_id="call_a", name="inspect", arguments="{}")],
        finish_reason="tool_calls",
    )]
    result = TurnStreamAssembler().consume(_stream(chunks))
    next_client, requests = _client([_delta_chunk(content="Read.", finish_reason="stop")])
    next_turn = OpenAIChatModelAdapter(client=next_client, model_name="deepseek-reasoner")
    TurnStreamAssembler().consume(next_turn.stream(messages=[
        {"role": "user", "content": "Read the source."},
        *result.output_items,
        {"type": "function_call_output", "call_id": "call_a", "output": "Observed."},
    ], tools=[]))

    assert result.reasoning_summary == ""
    assert result.display_text == "I'll check."
    assert requests.request is not None
    assistant, tool = requests.request["messages"][-2:]
    assert assistant["content"] == "I'll check."
    assert assistant["reasoning_content"] == "opaque continuation"
    assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"] == "call_a"


def test_chat_tool_images_are_native_content_after_all_tool_responses() -> None:
    image = "data:image/png;base64,aW1hZ2U="
    messages = to_chat_messages([
        {"type": "function_call", "call_id": "a", "name": "view", "arguments": "{}"},
        {"type": "function_call", "call_id": "b", "name": "inspect", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "a", "output": [
            {"type": "input_text", "text": "Observed"},
            {"type": "input_image", "image_url": image},
        ]},
        {"type": "function_call_output", "call_id": "b", "output": "Inspected"},
    ])
    assert [message["role"] for message in messages] == ["assistant", "tool", "tool", "user"]
    assert messages[1]["content"] == "Observed"
    assert messages[3]["content"][1]["image_url"]["url"] == image


def test_chat_request_uses_nested_tools_and_usage_stream_option() -> None:
    chunks = [_delta_chunk(finish_reason="stop")]
    client, completions = _client(chunks)
    adapter = OpenAIChatModelAdapter(client=client, model_name="deepseek-chat")
    schema = {
        "type": "function",
        "name": "sql_validate",
        "description": "Validate SQL",
        "parameters": {"type": "object", "properties": {}},
    }

    list(
        adapter.stream(
            messages=[{"role": "user", "content": "hi"}],
            tools=project_tool_schemas(
                PROVIDER_CHAT, model_name="deepseek-chat", tools=[schema]
            ),
        )
    )

    assert completions.request is not None
    assert completions.request["stream"] is True
    assert completions.request["stream_options"] == {"include_usage": True}
    assert completions.request["tools"][0]["type"] == "function"
    assert completions.request["tools"][0]["function"]["name"] == "sql_validate"
    assert "strict" not in completions.request["tools"][0]["function"]


def test_transcript_messages_merge_assistant_calls_and_tool_outputs() -> None:
    messages = to_chat_messages(
        [
            {"role": "system", "content": "policy"},
            {"role": "user", "content": "question"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "working"}],
            },
            {
                "type": "function_call",
                "call_id": "call_a",
                "name": "sql_validate",
                "arguments": '{"sql":"SELECT 1"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_a",
                "output": '{"status":"succeeded"}',
            },
            {"type": "reasoning", "summary": []},
        ]
    )

    assert messages[0] == {"role": "system", "content": "policy"}
    assert messages[1] == {"role": "user", "content": "question"}
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "working"
    assert messages[2]["tool_calls"][0]["id"] == "call_a"
    assert messages[3] == {
        "role": "tool",
        "tool_call_id": "call_a",
        "content": '{"status":"succeeded"}',
    }


def test_request_json_provider_selects_chat_settings() -> None:
    run = AgentRun(
        id="run-1",
        session_id="session-1",
        question="q",
        request_json='{"provider":"openai-chat"}',
        llm_credential_id="credential-1",
        model_name="deepseek-chat",
    )

    settings = ProviderSettings.from_run(run)

    assert settings.provider == PROVIDER_CHAT


def test_explicit_run_provider_overrides_the_default() -> None:
    run = AgentRun(
        id="run-3",
        session_id="session-1",
        question="q",
        request_json='{"provider":"openai-responses"}',
        llm_credential_id="credential-1",
        api_base="https://api.deepseek.com/v1",
        model_name="deepseek-chat",
    )

    settings = ProviderSettings.from_run(run)

    assert settings.provider == PROVIDER_RESPONSES


def test_unknown_provider_is_rejected_before_projection() -> None:
    with pytest.raises(LlmConfigurationError) as raised:
        project_tool_schemas("anthropic-messages", model_name="x", tools=[])

    assert raised.value.code == "MODEL_PROVIDER_UNSUPPORTED"
