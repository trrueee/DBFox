"""OpenAI-compatible Chat Completions adapter for third-party model services."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, cast

from openai import AsyncOpenAI

from engine.agent.providers.plumbing import (
    ProviderProtocolError,
    ProviderWatchdogTimeout,
    await_provider_request,
    classify_provider_failure,
    close_async_resource,
    next_event_or_cancel,
)
from engine.agent.turn import (
    ModelStreamTimeouts,
    TurnStreamCancelled,
    TurnStreamItem,
    TurnStreamKind,
    TurnTermination,
)
from engine.app.safe_errors import (
    FixedErrorCode,
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.llm.config import LlmConfig
from engine.llm.providers.openai import create_openai_async_client

logger = logging.getLogger("dbfox.agent.provider.openai_chat")
MAX_ANSWER_DELTA_CHARS = 96
MAX_REASONING_CONTINUATION_BYTES = 512 * 1024


class ChatProtocolError(ProviderProtocolError):
    """Raised when a Chat Completions stream violates its documented lifecycle."""


def project_chat_tools(
    *,
    model_name: str | None,
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Nest the frozen Responses function schema for Chat Completions.

    The model name is intentionally unused: unlike the Responses protocol there
    is no deferred-tool-search form to project.  Keeping the signature aligned
    lets the Runtime own one provider-keyed projection table.
    """

    del model_name
    projected: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        projected.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("parameters")
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return projected


def to_chat_messages(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert durable provider transcript items into Chat Completions messages."""

    messages: list[dict[str, Any]] = []
    pending_assistant: dict[str, Any] | None = None
    tool_media: list[dict[str, Any]] = []

    def flush_assistant() -> None:
        nonlocal pending_assistant
        if pending_assistant is not None:
            messages.append(pending_assistant)
            pending_assistant = None

    for item in items:
        item_type = item.get("type")
        if tool_media and item_type != "function_call_output":
            messages.append({"role": "user", "content": tool_media})
            tool_media = []
        if item_type == "function_call":
            call_id = str(item.get("call_id") or "")
            name = str(item.get("name") or "")
            if not call_id or not name:
                continue
            if pending_assistant is None:
                pending_assistant = {"role": "assistant", "content": None}
            pending_assistant.setdefault("tool_calls", []).append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": str(item.get("arguments") or "{}"),
                    },
                }
            )
        elif item_type == "function_call_output":
            flush_assistant()
            text, images = _chat_tool_output(item.get("output"))
            call_id = str(item.get("call_id") or "")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": text,
                }
            )
            if images:
                # The Chat tool role accepts text only. Keep all tool outputs
                # adjacent, then attach the observed images as user media.
                tool_media.append({"type": "text", "text": f"Observed image for tool call {call_id}."})
                tool_media.extend(images)
        elif item_type == "reasoning":
            continuation = item.get("reasoning_content")
            if isinstance(continuation, str) and continuation:
                if pending_assistant is None:
                    pending_assistant = {"role": "assistant", "content": None}
                pending_assistant["reasoning_content"] = continuation
        elif item_type == "message":
            role = str(item.get("role") or "assistant")
            text = _message_text(item)
            if role == "assistant":
                if pending_assistant is not None:
                    flush_assistant()
                pending_assistant = {"role": "assistant", "content": text}
            else:
                flush_assistant()
                messages.append({"role": role, "content": text})
        elif item_type in {"tool_search_call", "tool_search_output"}:
            # Responses-only bookkeeping has no Chat Completions equivalent.
            continue
        elif "role" in item:
            flush_assistant()
            messages.append(
                {
                    "role": str(item["role"]),
                    "content": str(item.get("content") or ""),
                }
            )
    flush_assistant()
    if tool_media:
        messages.append({"role": "user", "content": tool_media})
    return messages


def _chat_tool_output(output: object) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(output, list):
        return str(output or ""), []
    text: list[str] = []
    images: list[dict[str, Any]] = []
    for part in output:
        if not isinstance(part, dict):
            raise ChatProtocolError("Invalid Chat tool output content part")
        if part.get("type") == "input_text" and isinstance(part.get("text"), str):
            text.append(part["text"])
        elif part.get("type") == "input_image" and isinstance(part.get("image_url"), str):
            images.append({
                "type": "image_url",
                "image_url": {"url": part["image_url"], "detail": part.get("detail", "auto")},
            })
        else:
            raise ChatProtocolError("Unsupported Chat tool output content part")
    return "\n".join(text), images


def _message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") in {"output_text", "input_text", "text"}:
            parts.append(str(part.get("text") or ""))
        elif part.get("type") == "refusal":
            parts.append(str(part.get("refusal") or ""))
    return "".join(parts)


def _usage_dict(usage: object) -> dict[str, int]:
    if usage is None:
        return {}
    normalized: dict[str, int] = {}
    for source, target in (
        ("prompt_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = getattr(usage, source, None)
        if value is not None:
            normalized[target] = int(value)
    # Keep the canonical Responses names too: the Run ledger accepts either.
    for source in ("prompt_tokens", "completion_tokens"):
        value = getattr(usage, source, None)
        if value is not None:
            normalized[source] = int(value)
    return normalized


@dataclass
class _AnswerState:
    item_id: str = "chat-answer-0"
    output_index: int = 0
    parts: list[str] = field(default_factory=list)
    started: bool = False
    ended: bool = False


@dataclass
class _ToolCallState:
    index: int
    call_id: str
    id_is_provider: bool
    name: str = ""
    arguments: str = ""
    ended: bool = False


@dataclass
class _ChatStreamTranslator:
    revisions: dict[str, int] = field(default_factory=dict)
    answer: _AnswerState = field(default_factory=_AnswerState)
    calls: dict[int, _ToolCallState] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_parts: list[str] = field(default_factory=list)
    reasoning_bytes: int = 0
    finish_reason: str | None = None
    terminal: bool = False

    def translate(self, chunk: object) -> Iterator[TurnStreamItem]:
        if self.terminal:
            raise ChatProtocolError("Chat stream emitted an item after termination")
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            self.usage = _usage_dict(usage)
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is not None:
            continuation = getattr(delta, "reasoning_content", None)
            if isinstance(continuation, str) and continuation:
                self.reasoning_bytes += len(continuation.encode("utf-8"))
                if self.reasoning_bytes > MAX_REASONING_CONTINUATION_BYTES:
                    raise ChatProtocolError("Chat reasoning continuation exceeds its byte budget")
                self.reasoning_parts.append(continuation)
            content = getattr(delta, "content", None)
            if isinstance(content, str) and content:
                yield from self._answer_delta(content)
            for call in getattr(delta, "tool_calls", None) or []:
                yield from self._tool_delta(call)
        reason = getattr(choice, "finish_reason", None)
        if reason is not None:
            if self.finish_reason is not None and self.finish_reason != reason:
                raise ChatProtocolError("Chat finish reason changed mid-stream")
            self.finish_reason = str(reason)

    def finalize(self) -> Iterator[TurnStreamItem]:
        if self.terminal:
            return
        output_index = 0
        if self.answer.started and not self.answer.ended:
            self.answer.ended = True
            yield self._emit(
                TurnStreamKind.ANSWER_END,
                self.answer.item_id,
                output_index=self.answer.output_index,
                phase=None,
                message_status=(
                    "incomplete" if self.finish_reason == "length" else "completed"
                ),
            )
            yield self._emit(
                TurnStreamKind.MODEL_OUTPUT_ITEM,
                self.answer.item_id,
                output_index=output_index,
                model_output_item={
                    "type": "message", "role": "assistant", "content": "".join(self.answer.parts),
                },
            )
            output_index += 1
        if self.calls and self.reasoning_parts:
            yield self._emit(
                TurnStreamKind.MODEL_OUTPUT_ITEM,
                "chat-continuation",
                output_index=output_index,
                model_output_item={
                    "type": "reasoning", "reasoning_content": "".join(self.reasoning_parts),
                },
            )
            output_index += 1
        for index in sorted(self.calls):
            state = self.calls[index]
            if not state.name:
                yield self._error(
                    "MODEL_PROVIDER_PROTOCOL_ERROR",
                    "模型服务返回了缺少名称的工具调用。",
                    retryable=False,
                )
                return
            state.ended = True
            yield self._emit(
                TurnStreamKind.TOOL_CALL_END,
                f"chat-tool-{index}",
                tool_call_index=index,
            )
            yield self._emit(
                TurnStreamKind.MODEL_OUTPUT_ITEM,
                f"chat-tool-item-{index}",
                output_index=output_index + index,
                model_output_item={
                    "type": "function_call",
                    "id": f"fc_{state.call_id}",
                    "call_id": state.call_id,
                    "name": state.name,
                    "arguments": state.arguments or "{}",
                    "status": "completed",
                },
            )
        if self.usage:
            yield self._emit(TurnStreamKind.USAGE, "usage", usage=self.usage)
        reason = self.finish_reason
        if reason is None:
            yield self._error(
                FixedErrorCode.MODEL_PROVIDER_STREAM_TRUNCATED.value,
                fixed_error_detail(FixedErrorCode.MODEL_PROVIDER_STREAM_TRUNCATED)["message"],
                retryable=True,
            )
            return
        if reason == "length":
            termination = TurnTermination.INCOMPLETE
        elif reason in {"content_filter", "error"}:
            termination = TurnTermination.FAILED
        else:
            termination = TurnTermination.COMPLETED
        self.terminal = True
        yield self._emit(TurnStreamKind.FINISH, "finish", termination=termination)

    def failed_stream_item(self, failure: object) -> TurnStreamItem:
        self.terminal = True
        return self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code=getattr(failure, "code", "MODEL_PROVIDER_STREAM_FAILED"),
            error_message=getattr(failure, "message", "模型服务调用失败。"),
            error_retryable=getattr(failure, "retryable", False),
            retry_after_seconds=getattr(failure, "retry_after_seconds", None),
        )

    def _emit(self, kind: TurnStreamKind, item_id: str, **values: Any) -> TurnStreamItem:
        revision = self.revisions.get(item_id, 0) + 1
        self.revisions[item_id] = revision
        return TurnStreamItem(kind=kind, item_id=item_id, revision=revision, **values)

    def _answer_delta(self, content: str) -> Iterator[TurnStreamItem]:
        if not self.answer.started:
            self.answer.started = True
            yield self._emit(
                TurnStreamKind.ANSWER_START,
                self.answer.item_id,
                output_index=self.answer.output_index,
                phase=None,
            )
        if self.answer.ended:
            raise ChatProtocolError("Chat text delta arrived after answer completion")
        self.answer.parts.append(content)
        for start in range(0, len(content), MAX_ANSWER_DELTA_CHARS):
            yield self._emit(
                TurnStreamKind.ANSWER_DELTA,
                self.answer.item_id,
                content=content[start : start + MAX_ANSWER_DELTA_CHARS],
            )

    def _tool_delta(self, call: object) -> Iterator[TurnStreamItem]:
        index = getattr(call, "index", None)
        if not isinstance(index, int) or index < 0:
            raise ChatProtocolError("Chat tool call is missing its index")
        function = getattr(call, "function", None)
        name = getattr(function, "name", None) if function is not None else None
        arguments = getattr(function, "arguments", None) if function is not None else None
        provider_id = getattr(call, "id", None)
        state = self.calls.get(index)
        if state is None:
            state = _ToolCallState(
                index=index,
                call_id=str(provider_id or f"call_{index}"),
                id_is_provider=bool(provider_id),
                name=str(name or ""),
            )
            self.calls[index] = state
            yield self._emit(
                TurnStreamKind.TOOL_CALL_START,
                f"chat-tool-{index}",
                tool_call_index=index,
                tool_call_id=state.call_id,
                tool_name=state.name or None,
            )
        else:
            if provider_id and not state.id_is_provider:
                state.call_id = str(provider_id)
                state.id_is_provider = True
                yield self._emit(
                    TurnStreamKind.TOOL_CALL_DELTA,
                    f"chat-tool-{index}",
                    tool_call_index=index,
                    tool_call_id=state.call_id,
                )
            if name and not state.name:
                state.name = str(name)
                yield self._emit(
                    TurnStreamKind.TOOL_CALL_DELTA,
                    f"chat-tool-{index}",
                    tool_call_index=index,
                    tool_name=state.name,
                )
        if arguments:
            state.arguments += str(arguments)
            yield self._emit(
                TurnStreamKind.TOOL_CALL_DELTA,
                f"chat-tool-{index}",
                tool_call_index=index,
                arguments_delta=str(arguments),
            )

    def _error(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
    ) -> TurnStreamItem:
        self.terminal = True
        return self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code=code,
            error_message=message,
            error_retryable=retryable,
        )


class OpenAIChatModelAdapter:
    """Lower Chat Completions chunks into DBFox's provider-neutral Turn stream."""

    provider_id = "openai-chat"

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_name: str,
        owns_client: bool = False,
        max_output_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.model_name = model_name
        self._owns_client = owns_client
        self._max_output_tokens = max_output_tokens
        self._extra_body = extra_body

    @classmethod
    def from_config(cls, config: LlmConfig) -> "OpenAIChatModelAdapter":
        return cls(
            client=create_openai_async_client(
                api_key=config.api_key,
                api_base=config.api_base,
            ),
            model_name=config.model_name,
            owns_client=True,
        )

    def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout_seconds: float | None = None,
        stream_timeouts: ModelStreamTimeouts | None = None,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> Iterator[TurnStreamItem]:
        if stream_timeouts is None:
            turn_seconds = (
                max(0.01, timeout_seconds) if timeout_seconds is not None else 180.0
            )
            stream_timeouts = ModelStreamTimeouts(
                turn_seconds=turn_seconds,
                first_event_seconds=min(30.0, turn_seconds),
                idle_seconds=min(60.0, turn_seconds),
                request_seconds=min(60.0, turn_seconds),
            )
        request: dict[str, Any] = {
            "model": self.model_name,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        if self._max_output_tokens is not None:
            request["max_tokens"] = self._max_output_tokens
        if self._extra_body is not None:
            request["extra_body"] = self._extra_body
        request["timeout"] = max(0.01, stream_timeouts.turn_seconds)

        translator = _ChatStreamTranslator()
        runner = asyncio.Runner()
        events: AsyncIterator[Any] | None = None
        turn_deadline = time.monotonic() + stream_timeouts.turn_seconds
        try:
            request["messages"] = to_chat_messages(messages)
            events = cast(
                AsyncIterator[Any],
                runner.run(
                    await_provider_request(
                        self.client.chat.completions.create(**request),
                        cancellation_probe,
                        timeout_seconds=min(
                            stream_timeouts.request_seconds,
                            max(0.01, turn_deadline - time.monotonic()),
                        ),
                    )
                ),
            )
            iterator = events.__aiter__()
            first_event = True
            while True:
                try:
                    remaining = turn_deadline - time.monotonic()
                    if remaining <= 0:
                        raise ProviderWatchdogTimeout(
                            FixedErrorCode.MODEL_PROVIDER_TURN_TIMEOUT
                        )
                    phase_timeout = (
                        stream_timeouts.first_event_seconds
                        if first_event
                        else stream_timeouts.idle_seconds
                    )
                    chunk = runner.run(
                        next_event_or_cancel(
                            iterator,
                            cancellation_probe,
                            timeout_seconds=min(phase_timeout, remaining),
                            timeout_code=(
                                FixedErrorCode.MODEL_PROVIDER_FIRST_EVENT_TIMEOUT
                                if first_event
                                else FixedErrorCode.MODEL_PROVIDER_STREAM_IDLE_TIMEOUT
                            ),
                        )
                    )
                    first_event = False
                except StopAsyncIteration:
                    break
                yield from translator.translate(chunk)
            yield from translator.finalize()
        except TurnStreamCancelled:
            raise
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_MODEL_PROVIDER_STREAM,
                exc=exc,
            )
            yield translator.failed_stream_item(classify_provider_failure(exc))
        finally:
            if events is not None:
                with suppress(Exception):
                    runner.run(close_async_resource(events))
            if self._owns_client:
                with suppress(Exception):
                    runner.run(close_async_resource(self.client))
            runner.close()
