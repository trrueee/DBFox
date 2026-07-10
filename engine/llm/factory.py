"""LLM client factory - single entry point for model client construction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from engine.llm.config import LlmConfig
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
