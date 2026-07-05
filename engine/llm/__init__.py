"""DBFox LLM Infrastructure — provider-agnostic model access.

Dependency rule:
    engine.llm has NO internal project dependencies.
    It is consumed by agent, semantic, sql, and evaluation layers.
"""

from engine.llm.config import (
    LlmConfig,
    LlmConfigurationError,
    resolve_optional_product_llm_config,
    resolve_product_llm_config,
    resolve_support_llm_config_from_env,
)
from engine.llm.factory import LLMClientFactory, LlmCallOptions, create_chat_model, get_chat_model
from engine.llm.structured import with_structured_output

__all__ = [
    "LLMClientFactory",
    "LlmCallOptions",
    "LlmConfig",
    "LlmConfigurationError",
    "create_chat_model",
    "get_chat_model",
    "resolve_optional_product_llm_config",
    "resolve_product_llm_config",
    "resolve_support_llm_config_from_env",
    "with_structured_output",
]
