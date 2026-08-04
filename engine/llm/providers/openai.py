"""OpenAI client construction for the Responses API runtime."""
from __future__ import annotations

from typing import TYPE_CHECKING

from engine.llm.endpoint_policy import resolve_runtime_llm_endpoint
from engine.llm.http_clients import create_llm_async_http_client, get_llm_http_clients

if TYPE_CHECKING:
    from openai import AsyncOpenAI, OpenAI


def create_openai_responses_client(
    *,
    api_key: str,
    api_base: str,
    timeout: float = 120.0,
) -> "OpenAI":
    """Build the synchronous OpenAI SDK client behind the common LLM boundary.

    Keeping construction here ensures every model call receives the same
    runtime DNS/IP admission check and application-owned transport. In
    particular, the bearer credential must never be
    sent through an environment proxy or followed to a redirect target.
    """

    from openai import OpenAI

    endpoint = resolve_runtime_llm_endpoint(api_base)
    http_client, _http_async_client = get_llm_http_clients(
        endpoint=endpoint,
        timeout=timeout,
    )
    return OpenAI(
        api_key=api_key,
        base_url=endpoint.api_base,
        timeout=timeout,
        max_retries=0,
        http_client=http_client,
    )


def create_openai_responses_async_client(
    *,
    api_key: str,
    api_base: str,
    timeout: float = 120.0,
) -> "AsyncOpenAI":
    """Build an async Responses client owned by one Agent adapter."""

    from openai import AsyncOpenAI

    endpoint = resolve_runtime_llm_endpoint(api_base)
    http_client = create_llm_async_http_client(endpoint=endpoint, timeout=timeout)
    return AsyncOpenAI(
        api_key=api_key,
        base_url=endpoint.api_base,
        timeout=timeout,
        max_retries=0,
        http_client=http_client,
    )
