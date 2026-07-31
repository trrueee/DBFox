"""DBFox LLM Infrastructure — provider-agnostic model access.

Dependency rule:
    engine.llm has NO internal project dependencies.
    It is consumed by agent, semantic, and SQL layers.
"""

from engine.llm.config import (
    LlmConfig,
    LlmConfigurationError,
    resolve_product_llm_config_from_credential,
)
from engine.llm.factory import create_openai_compatible_client

__all__ = [
    "LlmConfig",
    "LlmConfigurationError",
    "create_openai_compatible_client",
    "resolve_product_llm_config_from_credential",
]
