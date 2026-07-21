from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.turn import TurnStreamAssembler, TurnStreamCancelled, TurnStreamKind


class _Completions:
    def __init__(self, chunks: list[object]) -> None:
        self.chunks = chunks
        self.request: dict[str, object] | None = None

    def create(self, **request: object):
        self.request = request
        return iter(self.chunks)


class _Client:
    def __init__(self, chunks: list[object]) -> None:
        self.completions = _Completions(chunks)
        self.chat = SimpleNamespace(completions=self.completions)


def test_openai_adapter_normalizes_text_reasoning_tool_calls_and_usage() -> None:
    client = _Client(
        [
            {
                "choices": [
                    {
                        "delta": {
                            "content": "先检查",
                            "reasoning_content": "provider private scratchpad",
                            "reasoning_summary": "正在确认所需数据。",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {
                                        "name": "sql.execute_readonly",
                                        "arguments": '{"sql":"SELECT ',
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": '1"}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            },
        ]
    )
    adapter = OpenAIModelAdapter(client=client, model_name="test-model")

    items = list(
        adapter.stream(
            messages=[{"role": "user", "content": "查一下"}],
            tools=[{"type": "function", "function": {"name": "sql.execute_readonly"}}],
        )
    )
    result = TurnStreamAssembler().consume(items)

    assert result.text == "先检查"
    assert result.reasoning_summary == "正在确认所需数据。"
    assert "private scratchpad" not in result.reasoning_summary
    assert result.tool_calls[0].arguments == {"sql": "SELECT 1"}
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    assert result.finish_signal == "tool_calls"
    assert client.completions.request == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "查一下"}],
        "stream": True,
        "tools": [{"type": "function", "function": {"name": "sql.execute_readonly"}}],
        "tool_choice": "auto",
    }
    assert [item.kind for item in items].count(TurnStreamKind.TOOL_CALL_END) == 1


def test_openai_adapter_emits_safe_error_item() -> None:
    class _FailingCompletions:
        def create(self, **_request: object):
            raise RuntimeError("secret provider detail")

    client = SimpleNamespace(chat=SimpleNamespace(completions=_FailingCompletions()))
    adapter = OpenAIModelAdapter(client=client, model_name="test-model")

    item = list(adapter.stream(messages=[], tools=[]))[0]

    assert item.kind is TurnStreamKind.ERROR
    assert item.error_code == "MODEL_PROVIDER_STREAM_FAILED"
    assert "secret provider detail" not in (item.error_message or "")


@pytest.mark.parametrize(
    ("provider", "chunk"),
    [
        ("openai", {"choices": [{"delta": {"content": "OpenAI"}, "finish_reason": "stop"}]}),
        ("qwen", SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Qwen"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )),
        ("deepseek", {
            "choices": [{
                "delta": {"content": "DeepSeek", "reasoning_content": "private chain of thought"},
                "finish_reason": "stop",
            }],
        }),
        ("openrouter", {
            "choices": [{"delta": {"content": "OpenRouter"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
        }),
    ],
)
def test_openai_compatible_provider_conformance(provider: str, chunk: object) -> None:
    client = _Client([chunk])
    result = TurnStreamAssembler().consume(OpenAIModelAdapter(
        client=client, model_name=f"{provider}-model",
    ).stream(messages=[], tools=[], timeout_seconds=9))

    assert result.text == {
        "openai": "OpenAI", "qwen": "Qwen", "deepseek": "DeepSeek", "openrouter": "OpenRouter",
    }[provider]
    assert "private chain of thought" not in result.reasoning_summary
    assert client.completions.request["timeout"] == 9


def test_provider_stream_honors_cancellation_before_publishing_a_chunk() -> None:
    client = _Client([{"choices": [{"delta": {"content": "must not publish"}, "finish_reason": "stop"}]}])
    adapter = OpenAIModelAdapter(client=client, model_name="cancel-model")

    with pytest.raises(TurnStreamCancelled, match="cancelled"):
        list(adapter.stream(messages=[], tools=[], cancellation_probe=lambda: True))
