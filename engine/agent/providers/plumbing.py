"""Provider-agnostic request admission, stream watchdogs, and failure mapping."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress

from openai import APIConnectionError, APITimeoutError, APIStatusError

from engine.agent.turn import TurnStreamCancelled
from engine.app.safe_errors import FixedErrorCode
from engine.llm.providers.openai import (
    ProviderFailure,
    classify_openai_status_error,
    provider_failure,
)


class ProviderProtocolError(RuntimeError):
    """A provider stream violated its documented item lifecycle."""


class ProviderWatchdogTimeout(TimeoutError):
    def __init__(self, code: FixedErrorCode) -> None:
        from engine.app.safe_errors import fixed_error_detail

        super().__init__(fixed_error_detail(code)["message"])
        self.code = code


async def await_provider_request(
    request: Awaitable[object],
    cancellation_probe: Callable[[], bool] | None,
    *,
    timeout_seconds: float,
) -> object:
    """Await request admission/response headers with cancellation and a deadline."""

    task: asyncio.Future[object] = asyncio.ensure_future(request)
    deadline = asyncio.get_running_loop().time() + max(0.01, timeout_seconds)
    try:
        while True:
            if cancellation_probe and cancellation_probe():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise TurnStreamCancelled("Model provider request was cancelled")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise ProviderWatchdogTimeout(
                    FixedErrorCode.MODEL_PROVIDER_REQUEST_TIMEOUT
                )
            done, _pending = await asyncio.wait({task}, timeout=min(0.05, remaining))
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def next_event_or_cancel(
    events: AsyncIterator[object],
    cancellation_probe: Callable[[], bool] | None,
    *,
    timeout_seconds: float,
    timeout_code: FixedErrorCode,
) -> object:
    task: asyncio.Future[object] = asyncio.ensure_future(anext(events))
    deadline = asyncio.get_running_loop().time() + max(0.01, timeout_seconds)
    try:
        while True:
            if cancellation_probe and cancellation_probe():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise TurnStreamCancelled("Model provider stream was cancelled")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise ProviderWatchdogTimeout(timeout_code)
            done, _pending = await asyncio.wait({task}, timeout=min(0.05, remaining))
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def close_async_resource(resource: object) -> None:
    close = getattr(resource, "close", None) or getattr(resource, "aclose", None)
    if not callable(close):
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def classify_provider_failure(exc: Exception) -> ProviderFailure:
    if isinstance(exc, ProviderWatchdogTimeout):
        return provider_failure(exc.code, True)
    if isinstance(exc, APITimeoutError):
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_TIMEOUT, True)
    if isinstance(exc, APIConnectionError):
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_UNAVAILABLE, True)
    if isinstance(exc, APIStatusError):
        return classify_openai_status_error(exc)
    if isinstance(exc, ProviderProtocolError):
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_PROTOCOL_ERROR, False)
    return provider_failure(FixedErrorCode.MODEL_PROVIDER_STREAM_FAILED, False)
