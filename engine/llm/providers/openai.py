"""OpenAI Responses clients and safe HTTP failure classification."""
from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from openai import APIStatusError

from engine.app.safe_errors import FixedErrorCode, fixed_error_detail

from engine.llm.endpoint_policy import resolve_runtime_llm_endpoint
from engine.llm.http_clients import create_llm_async_http_client, get_llm_http_clients

if TYPE_CHECKING:
    from openai import AsyncOpenAI, OpenAI


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    message: str
    retryable: bool
    retry_after_seconds: float | None = None


def provider_failure(
    code: FixedErrorCode,
    retryable: bool,
    retry_after_seconds: float | None = None,
) -> ProviderFailure:
    detail = fixed_error_detail(code)
    return ProviderFailure(
        code=detail["code"], message=detail["message"], retryable=retryable,
        retry_after_seconds=retry_after_seconds,
    )


def classify_openai_status_error(exc: APIStatusError) -> ProviderFailure:
    """Share SDK status semantics between Agent calls and connection diagnostics."""
    status = exc.status_code
    if status == 402:
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_QUOTA_EXCEEDED, False)
    retry_after = _parse_retry_after(exc.response.headers.get("Retry-After"))
    if status == 429:
        if _structured_provider_error_code(exc) in _QUOTA_ERROR_CODES:
            return provider_failure(FixedErrorCode.MODEL_PROVIDER_QUOTA_EXCEEDED, False)
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_RATE_LIMITED, True, retry_after)
    if status in {408, 409, 425} or status >= 500:
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_UNAVAILABLE, True, retry_after)
    if status == 401:
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_AUTHENTICATION_FAILED, False)
    if status == 403:
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_PERMISSION_DENIED, False)
    if status == 404:
        return provider_failure(FixedErrorCode.MODEL_PROVIDER_MODEL_NOT_FOUND, False)
    return provider_failure(FixedErrorCode.MODEL_PROVIDER_REQUEST_REJECTED, False)


_QUOTA_ERROR_CODES = frozenset({
    "credit_balance_exhausted", "organization_spend_limit_exceeded",
    "organization_usage_limit_exceeded", "project_spend_limit_exceeded",
})


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
