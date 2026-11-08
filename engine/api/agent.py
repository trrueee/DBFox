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
from engine.llm.providers.openai import classify_openai_status_error, create_openai_responses_client
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


class LlmModelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_credential_id: str = Field(min_length=1, max_length=256)
    api_base: str = Field(min_length=1, max_length=2_048)


class LlmModelOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    owned_by: str | None = None


class LlmModelsResponse(BaseModel):
    ok: bool
    api_base: str
    models: list[LlmModelOption] = Field(default_factory=list, max_length=1_000)
    error_code: str | None = None
    error_message: str | None = None


def _probe_llm_service(*, client: Any, model_name: str) -> None:
    """Check the same native Responses endpoint used by the Agent runtime."""
    client.responses.create(model=model_name, input="ping", max_output_tokens=16, store=False)


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
        failure = classify_openai_status_error(exc) if isinstance(exc, APIStatusError) else None
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
            error_code=failure.code if failure else "LLM_CONNECTION_FAILED",
            error_message=failure.message if failure else "模型连接测试未通过，请检查服务地址、凭据和模型名称。",
        )

@router.post("/agent/llm/models", response_model=LlmModelsResponse)
def api_llm_models(req: LlmModelsRequest) -> LlmModelsResponse:
    """List the models an OpenAI-compatible endpoint currently exposes.

    Resolves the credential through the local OS vault, then queries the
    provider's ``/models`` route with the same client stack as the Agent
    runtime. Unsupported model routes and other failures return safe diagnostics.
    """
    try:
        config = resolve_product_llm_config_from_credential(
            llm_credential_id=req.llm_credential_id,
            api_base=req.api_base,
            model_name=DEFAULT_LLM_MODEL_NAME,
        )
        client = create_openai_responses_client(
            api_key=config.api_key,
            api_base=config.api_base,
            timeout=10.0,
        )
        page = client.models.list()
        options: list[LlmModelOption] = []
        seen: set[str] = set()
        for model in page.data:
            model_id = (model.id or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            options.append(LlmModelOption(id=model_id, owned_by=model.owned_by or None))
        options.sort(key=lambda option: option.id)
        return LlmModelsResponse(ok=True, api_base=config.api_base, models=options)
    except Exception as exc:
        failure = classify_openai_status_error(exc) if isinstance(exc, APIStatusError) else None
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.UNEXPECTED,
            exc=exc,
        )
        return LlmModelsResponse(
            ok=False,
            api_base=req.api_base,
            error_code=failure.code if failure else "LLM_MODEL_LIST_FAILED",
            error_message=failure.message if failure else "无法从该服务获取模型列表，请检查服务地址与凭据。",
        )

router.include_router(result_router)
