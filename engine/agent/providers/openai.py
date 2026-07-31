"""OpenAI Responses API adapter built on the SDK's typed event contract."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, cast

from openai import OpenAI
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

from engine.agent.turn import TurnStreamCancelled, TurnStreamItem, TurnStreamKind
from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.llm.config import LlmConfig
from engine.llm.providers.openai import create_openai_responses_client

logger = logging.getLogger("dbfox.agent.provider.openai")
MAX_ANSWER_DELTA_CHARS = 96


class ResponsesProtocolError(RuntimeError):
    """Raised when a typed Responses stream violates its documented lifecycle."""


@dataclass
class _MessageState:
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
                code="MODEL_PROVIDER_INCOMPLETE",
                message=(
                    "Model response was incomplete "
                    f"({event.response.incomplete_details.reason})."
                    if event.response.incomplete_details is not None
                    else "Model response was incomplete."
                ),
            )
        elif isinstance(event, (ResponseFailedEvent, ResponseErrorEvent)):
            yield self._response_error(
                code="MODEL_PROVIDER_FAILED",
                message="Model provider stream failed.",
            )

    def truncated_stream_items(self) -> Iterator[TurnStreamItem]:
        if self.reasoning_started and not self.reasoning_ended:
            yield self._end_reasoning()
        yield self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code="MODEL_PROVIDER_STREAM_TRUNCATED",
            error_message=(
                "Model provider stream ended without a terminal response event."
            ),
        )

    def failed_stream_item(self) -> TurnStreamItem:
        return self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code="MODEL_PROVIDER_STREAM_FAILED",
            error_message="Model provider stream failed.",
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
            self.messages[item.id] = _MessageState(phase=item.phase)
            yield self._emit(
                TurnStreamKind.ANSWER_START,
                item.id,
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
            yield from self._message_done(item)
        elif isinstance(item, ResponseFunctionToolCall):
            yield from self._function_call_done(event.output_index, item)

    def _message_done(
        self,
        item: ResponseOutputMessage,
    ) -> Iterator[TurnStreamItem]:
        state = self.messages.get(item.id)
        if state is None or state.ended:
            raise ResponsesProtocolError(
                f"Message completion is outside lifecycle: {item.id}"
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
            phase=item.phase,
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
            finish_signal=event.response.status or "completed",
        )

    def _end_reasoning(self) -> TurnStreamItem:
        self.reasoning_ended = True
        return self._emit(
            TurnStreamKind.REASONING_SUMMARY_END,
            "reasoning_summary",
        )

    def _response_error(self, *, code: str, message: str) -> TurnStreamItem:
        self.terminal = True
        return self._emit(
            TurnStreamKind.ERROR,
            "error",
            error_code=code,
            error_message=message,
        )


class OpenAIModelAdapter:
    """Lower official Responses SDK events into DBFox's provider-neutral Turn stream."""

    def __init__(self, *, client: OpenAI, model_name: str) -> None:
        self.client = client
        self.model_name = model_name

    @classmethod
    def from_config(cls, config: LlmConfig) -> "OpenAIModelAdapter":
        return cls(
            client=create_openai_responses_client(
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
        try:
            events = cast(
                Iterable[ResponseStreamEvent],
                self.client.responses.create(**request),
            )
            for event in events:
                if cancellation_probe and cancellation_probe():
                    close = getattr(events, "close", None)
                    if callable(close):
                        close()
                    raise TurnStreamCancelled("Model provider stream was cancelled")
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
            yield translator.failed_stream_item()
