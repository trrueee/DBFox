"""LLM client factory - single entry point for model client construction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from engine.llm.config import DEFAULT_LLM_API_BASE, DEFAULT_LLM_MODEL_NAME, LlmConfig
from engine.llm.providers.openai import create_openai_client


@dataclass(frozen=True)
class LlmCallOptions:
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 120.0


def create_chat_model(
    config: LlmConfig,
    options: LlmCallOptions | None = None,
) -> "ChatOpenAI":
    """Build a chat model from an already-resolved LLM configuration."""
    resolved_options = options or LlmCallOptions()
    return create_openai_client(
        model_name=config.model_name,
        api_key=config.api_key,
        api_base=config.api_base,
        temperature=resolved_options.temperature,
        max_tokens=resolved_options.max_tokens,
        timeout=resolved_options.timeout,
    )


@dataclass(frozen=True)
class LLMClientFactory:
    """Immutable factory bound to a specific provider config."""

    model_name: str
    api_key: str
    api_base: str

    def build(
        self,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> "ChatOpenAI":
        return create_chat_model(
            LlmConfig(
                model_name=self.model_name,
                api_key=self.api_key,
                api_base=self.api_base,
                source="product",
            ),
            LlmCallOptions(
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            ),
        )


def get_chat_model(
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    timeout: float = 120.0,
) -> "ChatOpenAI":
    """Compatibility wrapper for explicit-config product model calls.

    Environment-backed calls must go through
    ``resolve_support_llm_config_from_env()`` before reaching this factory.
    """
    config = LlmConfig(
        model_name=(model_name or DEFAULT_LLM_MODEL_NAME).strip(),
        api_key=(api_key or "").strip(),
        api_base=(api_base or DEFAULT_LLM_API_BASE).strip(),
        source="product",
    )
    return create_chat_model(
        config,
        LlmCallOptions(
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        ),
    )
