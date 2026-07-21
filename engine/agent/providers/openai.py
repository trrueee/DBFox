"""OpenAI-compatible provider adapter with normalized streaming output."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from engine.agent.turn import TurnStreamCancelled, TurnStreamItem, TurnStreamKind
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.llm.config import LlmConfig
from engine.llm.providers.openai import create_openai_compatible_api_client

logger = logging.getLogger("dbfox.agent.provider.openai")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class OpenAIModelAdapter:
    """Lower provider chunks to DBFox TurnStreamItem values."""

    def __init__(self, *, client: Any, model_name: str) -> None:
        self.client = client
        self.model_name = model_name

    @classmethod
    def from_config(cls, config: LlmConfig) -> "OpenAIModelAdapter":
        return cls(
            client=create_openai_compatible_api_client(
                api_key=config.api_key,
                api_base=config.api_base,
            ),
            model_name=config.model_name,
        )

    def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout_seconds: float | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> Iterator[TurnStreamItem]:
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        if timeout_seconds is not None:
            request["timeout"] = max(0.01, timeout_seconds)

        offsets: dict[str, int] = {}
        started_tool_calls: set[int] = set()

        def emit(kind: TurnStreamKind, channel: str, **values: Any) -> TurnStreamItem:
            offset = offsets.get(channel, 0)
            offsets[channel] = offset + 1
            return TurnStreamItem(kind=kind, channel=channel, offset=offset, **values)

        try:
            chunks: Iterable[Any] = self.client.chat.completions.create(**request)
            for chunk in chunks:
                if cancellation_probe and cancellation_probe():
                    close = getattr(chunks, "close", None)
                    if callable(close):
                        close()
                    raise TurnStreamCancelled("Model provider stream was cancelled")
                usage = _field(chunk, "usage")
                if usage is not None:
                    normalized_usage = {
                        key: int(value)
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                        if (value := _field(usage, key)) is not None
                    }
                    if normalized_usage:
                        yield emit(TurnStreamKind.USAGE, "meta", usage=normalized_usage)

                choices = _field(chunk, "choices", []) or []
                for choice in choices:
                    delta = _field(choice, "delta", {}) or {}
                    content = _field(delta, "content")
                    if isinstance(content, str) and content:
                        yield emit(TurnStreamKind.TEXT_DELTA, "text", content=content)

                    # Only an explicitly summarized provider field may cross
                    # the product boundary. reasoning_content/reasoning are
                    # provider scratchpads and must never become user-visible
                    # Activity text.
                    reasoning = _field(delta, "reasoning_summary")
                    if isinstance(reasoning, str) and reasoning:
                        yield emit(
                            TurnStreamKind.REASONING_SUMMARY_DELTA,
                            "reasoning_summary",
                            content=reasoning,
                        )

                    for fallback_index, tool_call in enumerate(_field(delta, "tool_calls", []) or []):
                        index = _field(tool_call, "index", fallback_index)
                        index = int(index if index is not None else fallback_index)
                        function = _field(tool_call, "function", {}) or {}
                        tool_call_id = _field(tool_call, "id")
                        tool_name = _field(function, "name")
                        arguments = _field(function, "arguments")
                        channel = f"tool:{index}"
                        if index not in started_tool_calls:
                            started_tool_calls.add(index)
                            yield emit(
                                TurnStreamKind.TOOL_CALL_START,
                                channel,
                                tool_call_index=index,
                                tool_call_id=str(tool_call_id) if tool_call_id else None,
                                tool_name=str(tool_name) if tool_name else None,
                                arguments_delta=str(arguments) if arguments else None,
                            )
                        else:
                            yield emit(
                                TurnStreamKind.TOOL_CALL_DELTA,
                                channel,
                                tool_call_index=index,
                                tool_call_id=str(tool_call_id) if tool_call_id else None,
                                tool_name=str(tool_name) if tool_name else None,
                                arguments_delta=str(arguments) if arguments else None,
                            )

                    finish_reason = _field(choice, "finish_reason")
                    if finish_reason is not None:
                        for index in sorted(started_tool_calls):
                            channel = f"tool:{index}"
                            yield emit(
                                TurnStreamKind.TOOL_CALL_END,
                                channel,
                                tool_call_index=index,
                            )
                        yield emit(
                            TurnStreamKind.FINISH,
                            "meta",
                            finish_signal=str(finish_reason),
                        )
        except TurnStreamCancelled:
            raise
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_MODEL_PROVIDER_STREAM,
                exc=exc,
            )
            yield emit(
                TurnStreamKind.ERROR,
                "meta",
                error_code="MODEL_PROVIDER_STREAM_FAILED",
                error_message="Model provider stream failed.",
            )
