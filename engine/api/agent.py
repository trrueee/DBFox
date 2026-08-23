"""Capability-neutral Agent diagnostics and artifact result endpoints."""

from __future__ import annotations

import logging
import time as _time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from openai import APIStatusError

from engine.app.safe_errors import (
    SafeLogOperation,
    log_unexpected_exception,
)
from engine.llm.config import DEFAULT_LLM_MODEL_NAME, resolve_product_llm_config_from_credential
from engine.agent.providers.openai import _responses_not_found_falls_back_to_chat
from engine.llm.providers.openai import create_openai_responses_client
from engine.api.agent_results import router as result_router

logger = logging.getLogger("dbfox.api.agent")
router = APIRouter()


class LlmTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_credential_id: str = Field(min_length=1, max_length=256)
    api_base: str = Field(min_length=1, max_length=2_048)
    model_name: str | None = Field(default=None, max_length=256)


class LlmTestResponse(BaseModel):
    ok: bool
    model: str
    api_base: str
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None


def _probe_llm_service(*, client: Any, model_name: str) -> None:
    """Probe the configured LLM endpoint with legacy-compatible fallback.

    DBFox runtime prefers Responses; if the endpoint does not expose it (404),
    fallback to Chat Completions, which is what many OpenAI-compatible
    gateways (including MiMo) currently support.
    """

    try:
        client.responses.create(
            model=model_name,
            input="ping",
            max_output_tokens=16,
            store=False,
        )
        return
    except APIStatusError as exc:
        if not _responses_not_found_falls_back_to_chat(exc):
            raise
        client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "ping"}],
            max_completion_tokens=16,
        )


@router.post("/agent/llm/test", response_model=LlmTestResponse)
def api_llm_test(req: LlmTestRequest) -> LlmTestResponse:
    """Test the exact Responses capability required by the Agent runtime.

    This endpoint resolves an opaque credential through the local OS vault and
    validates that it can reach the target LLM service.
    """
    t0 = _time.monotonic()
    try:
        config = resolve_product_llm_config_from_credential(
            llm_credential_id=req.llm_credential_id,
            api_base=req.api_base,
            model_name=req.model_name,
        )
        client = create_openai_responses_client(
            api_key=config.api_key,
            api_base=config.api_base,
            timeout=10.0,
        )
        _probe_llm_service(client=client, model_name=config.model_name)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        return LlmTestResponse(
            ok=True,
            model=config.model_name,
            api_base=config.api_base,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.UNEXPECTED,
            exc=exc,
        )
        return LlmTestResponse(
            ok=False,
            model=req.model_name or DEFAULT_LLM_MODEL_NAME,
            api_base=req.api_base,
            latency_ms=latency_ms,
            error_code="LLM_CONNECTION_FAILED",
            error_message="模型连接测试未通过，请检查服务地址、凭据和模型名称。",
        )

router.include_router(result_router)
