"""Capability-neutral Agent diagnostics and artifact result endpoints."""

from __future__ import annotations

import logging
import time as _time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from openai import APIStatusError

from engine.app.safe_errors import (
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.agent.turn import ModelStreamTimeouts, TurnStreamAssembler, TurnStreamError
from engine.llm.config import DEFAULT_LLM_MODEL_NAME, LlmConfigurationError, resolve_product_llm_config_from_credential
from engine.llm.local_model import ManagedLocalModel
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


class LocalModelStatus(BaseModel):
    mode: Literal["local", "remote"]
    model: str | None = None
    models_dir: str | None = None
    model_size_bytes: int | None = None
    context_length: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class LocalModelTestResponse(BaseModel):
    ok: bool
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None


def _local_model(request: Request) -> ManagedLocalModel | None:
    return getattr(request.app.state, "local_model", None)


def _require_cloud_mode(request: Request) -> None:
    model = _local_model(request)
    if model is not None and model.configured:
        raise HTTPException(status_code=409, detail=fixed_error_detail("LOCAL_MODEL_REQUIRED"))


@router.get("/agent/local-model", response_model=LocalModelStatus)
def api_local_model_status(request: Request) -> LocalModelStatus:
    model = _local_model(request)
    if model is None or not model.configured:
        return LocalModelStatus(mode="remote")
    profile = model.profile
    error = model.installation_error()
    return LocalModelStatus(
        mode="local",
        model=profile.model_name if profile else None,
        models_dir=str(profile.models_dir) if profile else None,
        model_size_bytes=profile.model_size_bytes if profile else None,
        context_length=profile.context_length if profile else None,
        error_code=error,
        error_message=fixed_error_detail(error)["message"] if error else None,
    )


@router.post("/agent/local-model/test", response_model=LocalModelTestResponse)
def api_local_model_test(request: Request) -> LocalModelTestResponse:
    started = _time.monotonic()
    error = None
    try:
        model = _local_model(request)
        if model is None:
            raise LlmConfigurationError("Local model missing", code="LOCAL_MODEL_NOT_CONFIGURED")
        result = TurnStreamAssembler().consume(model.adapter().stream(
            messages=[{"role": "user", "content": "只用中文回复：本地模型已就绪"}],
            tools=[],
            stream_timeouts=ModelStreamTimeouts(
                turn_seconds=120,
                request_seconds=90,
                first_event_seconds=60,
                idle_seconds=60,
            ),
        ))
        if not result.answer_text:
            error = "MODEL_PROVIDER_INCOMPLETE"
    except (LlmConfigurationError, TurnStreamError) as exc:
        error = exc.code
    return LocalModelTestResponse(
        ok=error is None,
        latency_ms=int((_time.monotonic() - started) * 1000),
        error_code=error,
        error_message=fixed_error_detail(error)["message"] if error else None,
    )


def _probe_llm_service(*, client: Any, model_name: str) -> None:
    """Check the same native Responses endpoint used by the Agent runtime."""
    client.responses.create(model=model_name, input="ping", max_output_tokens=16, store=False)


@router.post("/agent/llm/test", response_model=LlmTestResponse, dependencies=[Depends(_require_cloud_mode)])
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

@router.post("/agent/llm/models", response_model=LlmModelsResponse, dependencies=[Depends(_require_cloud_mode)])
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
