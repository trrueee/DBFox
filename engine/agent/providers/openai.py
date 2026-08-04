"""OpenAI Responses API adapter built on the SDK's typed event contract."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from collections.abc import Mapping
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.responses import (
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseIncompleteEvent,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseRefusalDeltaEvent,
    ResponseRefusalDoneEvent,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
)

from engine.agent.turn import (
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
from engine.llm.providers.openai import create_openai_responses_async_client

logger = logging.getLogger("dbfox.agent.provider.openai")
MAX_ANSWER_DELTA_CHARS = 96


class ResponsesProtocolError(RuntimeError):
    """Raised when a typed Responses stream violates its documented lifecycle."""


@dataclass(frozen=True)
class _ProviderFailure:
    code: str
    message: str
    retryable: bool
    retry_after_seconds: float | None = None


@dataclass
class _MessageState:
    output_index: int
    phase: str | None
    text: str = ""
    ended: bool = False


@dataclass
class _FunctionCallState:
    output_index: int
    call_id: str
    name: str
    arguments: str = ""
    ended: bool = False


def _completed_message_text(item: ResponseOutputMessage) -> str:
    return "".join(
        part.text if isinstance(part, ResponseOutputText) else part.refusal
        for part in item.content
        if isinstance(part, (ResponseOutputText, ResponseOutputRefusal))
    )


def _dump_output_item(item: ResponseOutputItem) -> dict[str, Any]:
    value = item.model_dump(mode="json", exclude_none=True)
    return cast(dict[str, Any], value)


@dataclass
class _ResponsesEventTranslator:
    """Validate and lower the official SDK event lifecycle into runtime items."""

    revisions: dict[str, int] = field(default_factory=dict)
    messages: dict[str, _MessageState] = field(default_factory=dict)
    calls: dict[str, _FunctionCallState] = field(default_factory=dict)
    reasoning_started: bool = False
    reasoning_ended: bool = False
    terminal: bool = False

    def translate(self, event: ResponseStreamEvent) -> Iterator[TurnStreamItem]:
        if isinstance(event, ResponseOutputItemAddedEvent):
            yield from self._item_added(event)
        elif isinstance(event, (ResponseTextDeltaEvent, ResponseRefusalDeltaEvent)):
            yield from self._answer_delta(event.item_id, event.delta)
        elif isinstance(event, ResponseRefusalDoneEvent):
            yield from self._refusal_done(event)
        elif isinstance(event, ResponseReasoningSummaryTextDeltaEvent):
            yield from self._reasoning_delta(event)
        elif isinstance(event, ResponseFunctionCallArgumentsDeltaEvent):
            yield from self._function_call_delta(event)
        elif isinstance(event, ResponseOutputItemDoneEvent):
            yield from self._item_done(event)
        elif isinstance(event, ResponseCompletedEvent):
            yield from self._response_completed(event)
        elif isinstance(event, ResponseIncompleteEvent):
            yield self._response_error(
                code=FixedErrorCode.MODEL_PROVIDER_INCOMPLETE,
            )
        elif isinstance(event, (ResponseFailedEvent, ResponseErrorEvent)):
            yield self._response_error(
                code=FixedErrorCode.MODEL_PROVIDER_FAILED,
            )

    def truncated_stream_items(self) -> Iterator[TurnStreamItem]:
        if self.reasoning_started and not self.reasoning_ended:
            yield self._end_reasoning()
        yield self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code=FixedErrorCode.MODEL_PROVIDER_STREAM_TRUNCATED.value,
            error_message=fixed_error_detail(
                FixedErrorCode.MODEL_PROVIDER_STREAM_TRUNCATED
            )["message"],
            error_retryable=True,
        )

    def failed_stream_item(self, failure: _ProviderFailure) -> TurnStreamItem:
        return self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code=failure.code,
            error_message=failure.message,
            error_retryable=failure.retryable,
            retry_after_seconds=failure.retry_after_seconds,
        )

    def _emit(
        self,
        kind: TurnStreamKind,
        item_id: str,
        **values: Any,
    ) -> TurnStreamItem:
        revision = self.revisions.get(item_id, 0) + 1
        self.revisions[item_id] = revision
        return TurnStreamItem(
            kind=kind,
            item_id=item_id,
            revision=revision,
            **values,
        )

    def _item_added(
        self,
        event: ResponseOutputItemAddedEvent,
    ) -> Iterator[TurnStreamItem]:
        item = event.item
        if isinstance(item, ResponseOutputMessage):
            if item.id in self.messages:
                raise ResponsesProtocolError(f"Message item started twice: {item.id}")
            self.messages[item.id] = _MessageState(
                output_index=event.output_index,
                phase=item.phase,
            )
            yield self._emit(
                TurnStreamKind.ANSWER_START,
                item.id,
                output_index=event.output_index,
                phase=item.phase,
            )
        elif isinstance(item, ResponseFunctionToolCall):
            item_id = item.id or item.call_id
            if item_id in self.calls:
                raise ResponsesProtocolError(
                    f"Function-call item started twice: {item_id}"
                )
            self.calls[item_id] = _FunctionCallState(
                output_index=event.output_index,
                call_id=item.call_id,
                name=item.name,
                arguments=item.arguments,
            )
            yield self._emit(
                TurnStreamKind.TOOL_CALL_START,
                item_id,
                tool_call_index=event.output_index,
                tool_call_id=item.call_id,
                tool_name=item.name,
            )
            if item.arguments:
                yield self._emit(
                    TurnStreamKind.TOOL_CALL_DELTA,
                    item_id,
                    tool_call_index=event.output_index,
                    arguments_delta=item.arguments,
                )

    def _answer_delta(
        self,
        item_id: str,
        content: str,
    ) -> Iterator[TurnStreamItem]:
        state = self.messages.get(item_id)
        if state is None or state.ended:
            raise ResponsesProtocolError(
                f"Text delta is outside message lifecycle: {item_id}"
            )
        state.text += content
        for start in range(0, len(content), MAX_ANSWER_DELTA_CHARS):
            yield self._emit(
                TurnStreamKind.ANSWER_DELTA,
                item_id,
                content=content[start : start + MAX_ANSWER_DELTA_CHARS],
            )

    def _refusal_done(
        self,
        event: ResponseRefusalDoneEvent,
    ) -> Iterator[TurnStreamItem]:
        state = self.messages.get(event.item_id)
        if state is None or state.ended:
            raise ResponsesProtocolError(
                f"Refusal completion is outside message lifecycle: {event.item_id}"
            )
        if not state.text:
            yield from self._answer_delta(event.item_id, event.refusal)
        elif state.text != event.refusal:
            raise ResponsesProtocolError(
                f"Refusal deltas do not match completed refusal: {event.item_id}"
            )

    def _reasoning_delta(
        self,
        event: ResponseReasoningSummaryTextDeltaEvent,
    ) -> Iterator[TurnStreamItem]:
        if self.reasoning_ended:
            raise ResponsesProtocolError(
                "Reasoning summary delta arrived after response completion"
            )
        if not self.reasoning_started:
            self.reasoning_started = True
            yield self._emit(
                TurnStreamKind.REASONING_SUMMARY_START,
                "reasoning_summary",
            )
        yield self._emit(
            TurnStreamKind.REASONING_SUMMARY_DELTA,
            "reasoning_summary",
            content=event.delta,
        )

    def _function_call_delta(
        self,
        event: ResponseFunctionCallArgumentsDeltaEvent,
    ) -> Iterator[TurnStreamItem]:
        state = self.calls.get(event.item_id)
        if state is None or state.ended:
            raise ResponsesProtocolError(
                f"Function arguments delta is outside call lifecycle: {event.item_id}"
            )
        if state.output_index != event.output_index:
            raise ResponsesProtocolError(
                f"Function call output index changed: {event.item_id}"
            )
        state.arguments += event.delta
        yield self._emit(
            TurnStreamKind.TOOL_CALL_DELTA,
            event.item_id,
            tool_call_index=event.output_index,
            arguments_delta=event.delta,
        )

    def _item_done(
        self,
        event: ResponseOutputItemDoneEvent,
    ) -> Iterator[TurnStreamItem]:
        item = event.item
        if isinstance(item, ResponseOutputMessage):
            yield from self._message_done(event.output_index, item)
        elif isinstance(item, ResponseFunctionToolCall):
            yield from self._function_call_done(event.output_index, item)

    def _message_done(
        self,
        output_index: int,
        item: ResponseOutputMessage,
    ) -> Iterator[TurnStreamItem]:
        state = self.messages.get(item.id)
        if state is None or state.ended:
            raise ResponsesProtocolError(
                f"Message completion is outside lifecycle: {item.id}"
            )
        if state.output_index != output_index:
            raise ResponsesProtocolError(
                f"Message output index changed: {item.id}"
            )
        completed_text = _completed_message_text(item)
        if not state.text and completed_text:
            yield from self._answer_delta(item.id, completed_text)
        elif state.text != completed_text:
            raise ResponsesProtocolError(
                f"Message deltas do not match completed message: {item.id}"
            )
        state.ended = True
        state.phase = item.phase
        yield self._emit(
            TurnStreamKind.ANSWER_END,
            item.id,
            output_index=output_index,
            phase=item.phase,
            message_status=item.status,
        )

    def _function_call_done(
        self,
        output_index: int,
        item: ResponseFunctionToolCall,
    ) -> Iterator[TurnStreamItem]:
        item_id = item.id or item.call_id
        state = self.calls.get(item_id)
        if state is None or state.ended:
            raise ResponsesProtocolError(
                f"Function-call completion is outside lifecycle: {item_id}"
            )
        if (
            state.output_index != output_index
            or state.call_id != item.call_id
            or state.name != item.name
        ):
            raise ResponsesProtocolError(
                f"Function-call identity changed before completion: {item_id}"
            )
        if not state.arguments and item.arguments:
            state.arguments = item.arguments
            yield self._emit(
                TurnStreamKind.TOOL_CALL_DELTA,
                item_id,
                tool_call_index=output_index,
                arguments_delta=item.arguments,
            )
        elif state.arguments != item.arguments:
            raise ResponsesProtocolError(
                f"Function arguments do not match completed call: {item_id}"
            )
        state.ended = True
        yield self._emit(
            TurnStreamKind.TOOL_CALL_END,
            item_id,
            tool_call_index=output_index,
            tool_call_id=item.call_id,
            tool_name=item.name,
        )

    def _response_completed(
        self,
        event: ResponseCompletedEvent,
    ) -> Iterator[TurnStreamItem]:
        if any(not state.ended for state in self.messages.values()):
            raise ResponsesProtocolError("Response completed with an open message item")
        if any(not state.ended for state in self.calls.values()):
            raise ResponsesProtocolError(
                "Response completed with an open function-call item"
            )
        for output_index, output_item in enumerate(event.response.output):
            item_id = getattr(output_item, "id", None) or f"output:{output_index}"
            yield self._emit(
                TurnStreamKind.MODEL_OUTPUT_ITEM,
                item_id,
                output_index=output_index,
                model_output_item=_dump_output_item(output_item),
            )
        if event.response.usage is not None:
            usage = event.response.usage
            yield self._emit(
                TurnStreamKind.USAGE,
                "usage",
                usage={
                    "prompt_tokens": usage.input_tokens,
                    "completion_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
            )
        if self.reasoning_started and not self.reasoning_ended:
            yield self._end_reasoning()
        self.terminal = True
        yield self._emit(
            TurnStreamKind.FINISH,
            "finish",
            termination=TurnTermination.COMPLETED,
        )

    def _end_reasoning(self) -> TurnStreamItem:
        self.reasoning_ended = True
        return self._emit(
            TurnStreamKind.REASONING_SUMMARY_END,
            "reasoning_summary",
        )

    def _response_error(self, *, code: FixedErrorCode) -> TurnStreamItem:
        self.terminal = True
        detail = fixed_error_detail(code)
        return self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code=detail["code"],
            error_message=detail["message"],
            error_retryable=False,
        )


class OpenAIModelAdapter:
    """Lower official Responses SDK events into DBFox's provider-neutral Turn stream."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model_name: str,
        owns_client: bool = False,
    ) -> None:
        self.client = client
        self.model_name = model_name
        self._owns_client = owns_client

    @classmethod
    def from_config(cls, config: LlmConfig) -> "OpenAIModelAdapter":
        return cls(
            client=create_openai_responses_async_client(
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
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> Iterator[TurnStreamItem]:
        request: dict[str, Any] = {
            "model": self.model_name,
            "input": messages,
            "stream": True,
            # DBFox owns the durable transcript, so provider-side state is disabled.
            "store": False,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
            # Approval and question interrupts require one durable call at a time.
            request["parallel_tool_calls"] = False
        if timeout_seconds is not None:
            request["timeout"] = max(0.01, timeout_seconds)

        translator = _ResponsesEventTranslator()
        runner = asyncio.Runner()
        events: AsyncIterator[ResponseStreamEvent] | None = None
        try:
            events = cast(
                AsyncIterator[ResponseStreamEvent],
                runner.run(self.client.responses.create(**request)),
            )
            iterator = events.__aiter__()
            while True:
                try:
                    event = runner.run(
                        _next_event_or_cancel(iterator, cancellation_probe)
                    )
                except StopAsyncIteration:
                    break
                yield from translator.translate(event)
                if translator.terminal:
                    return
            if not translator.terminal:
                yield from translator.truncated_stream_items()
        except TurnStreamCancelled:
            raise
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_MODEL_PROVIDER_STREAM,
                exc=exc,
            )
            yield translator.failed_stream_item(_classify_provider_failure(exc))
        finally:
            if events is not None:
                with suppress(Exception):
                    runner.run(_close_async_resource(events))
            if self._owns_client:
                with suppress(Exception):
                    runner.run(_close_async_resource(self.client))
            runner.close()


async def _next_event_or_cancel(
    events: AsyncIterator[ResponseStreamEvent],
    cancellation_probe: Callable[[], bool] | None,
) -> ResponseStreamEvent:
    task: asyncio.Future[ResponseStreamEvent] = asyncio.ensure_future(anext(events))
    try:
        while True:
            if cancellation_probe and cancellation_probe():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise TurnStreamCancelled("Model provider stream was cancelled")
            done, _pending = await asyncio.wait({task}, timeout=0.05)
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def _close_async_resource(resource: object) -> None:
    close = getattr(resource, "close", None) or getattr(resource, "aclose", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _classify_provider_failure(exc: Exception) -> _ProviderFailure:
    if isinstance(exc, APITimeoutError):
        return _provider_failure(FixedErrorCode.MODEL_PROVIDER_TIMEOUT, True)
    if isinstance(exc, APIConnectionError):
        return _provider_failure(FixedErrorCode.MODEL_PROVIDER_UNAVAILABLE, True)
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        retry_after = _parse_retry_after(exc.response.headers.get("Retry-After"))
        if status == 429:
            if _structured_provider_error_code(exc) in _QUOTA_ERROR_CODES:
                return _provider_failure(
                    FixedErrorCode.MODEL_PROVIDER_QUOTA_EXCEEDED,
                    False,
                )
            return _provider_failure(
                FixedErrorCode.MODEL_PROVIDER_RATE_LIMITED,
                True,
                retry_after,
            )
        if status in {408, 409, 425} or status >= 500:
            return _provider_failure(
                FixedErrorCode.MODEL_PROVIDER_UNAVAILABLE,
                True,
                retry_after,
            )
        if status == 401:
            return _provider_failure(
                FixedErrorCode.MODEL_PROVIDER_AUTHENTICATION_FAILED,
                False,
            )
        if status == 403:
            return _provider_failure(
                FixedErrorCode.MODEL_PROVIDER_PERMISSION_DENIED,
                False,
            )
        if status == 404:
            return _provider_failure(
                FixedErrorCode.MODEL_PROVIDER_MODEL_NOT_FOUND,
                False,
            )
        return _provider_failure(FixedErrorCode.MODEL_PROVIDER_REQUEST_REJECTED, False)
    if isinstance(exc, ResponsesProtocolError):
        return _provider_failure(FixedErrorCode.MODEL_PROVIDER_PROTOCOL_ERROR, False)
    return _provider_failure(FixedErrorCode.MODEL_PROVIDER_STREAM_FAILED, False)


_QUOTA_ERROR_CODES = frozenset({
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
    "project_spend_limit_exceeded",
})


def _provider_failure(
    code: FixedErrorCode,
    retryable: bool,
    retry_after_seconds: float | None = None,
) -> _ProviderFailure:
    detail = fixed_error_detail(code)
    return _ProviderFailure(
        code=detail["code"],
        message=detail["message"],
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
    )


def _structured_provider_error_code(exc: APIStatusError) -> str | None:
    """Read the SDK's structured error code without trusting provider text."""

    body = exc.body
    if not isinstance(body, Mapping):
        return None
    error = body.get("error")
    source = error if isinstance(error, Mapping) else body
    code = source.get("code")
    if not isinstance(code, str):
        return None
    normalized = code.strip().lower()
    return normalized or None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
