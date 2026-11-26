"""Model provider adapters and the provider-keyed tool schema projection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.agent.providers.openai import (
    OpenAIModelAdapter,
    project_responses_tools,
)
from engine.agent.providers.openai_chat import (
    OpenAIChatModelAdapter,
    project_chat_tools,
)
from engine.llm.config import LlmConfig, LlmConfigurationError

PROVIDER_RESPONSES = "openai-responses"
PROVIDER_CHAT = "openai-chat"
ToolProjector = Callable[..., list[dict[str, Any]]]
Adapter = OpenAIModelAdapter | OpenAIChatModelAdapter

_PROTOCOLS: dict[str, tuple[Callable[[LlmConfig], Adapter], ToolProjector]] = {
    PROVIDER_RESPONSES: (OpenAIModelAdapter.from_config, project_responses_tools),
    PROVIDER_CHAT: (OpenAIChatModelAdapter.from_config, project_chat_tools),
}
SUPPORTED_PROVIDERS = frozenset(_PROTOCOLS)


def _protocol(provider: str) -> tuple[Callable[[LlmConfig], Adapter], ToolProjector]:
    try:
        return _PROTOCOLS[provider]
    except KeyError as exc:
        raise LlmConfigurationError(
            "Unsupported model provider.", code="MODEL_PROVIDER_UNSUPPORTED",
        ) from exc


def build_provider_adapter(provider: str, config: LlmConfig) -> Adapter:
    factory, _ = _protocol(provider)
    return factory(config)


def project_tool_schemas(
    provider: str,
    *,
    model_name: str | None,
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project the frozen inventory for one provider without changing its hash."""

    _, projector = _protocol(provider)
    return projector(model_name=model_name, tools=tools)


__all__ = [
    "OpenAIChatModelAdapter",
    "OpenAIModelAdapter",
    "PROVIDER_CHAT",
    "PROVIDER_RESPONSES",
    "SUPPORTED_PROVIDERS",
    "build_provider_adapter",
    "project_chat_tools",
    "project_responses_tools",
    "project_tool_schemas",
]
