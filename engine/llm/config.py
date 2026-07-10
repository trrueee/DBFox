"""LLM configuration resolution boundaries."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from engine.errors import DBFoxError
from engine.security.credential_vault import CredentialKind, CredentialVault, get_credential_vault

DEFAULT_LLM_API_BASE = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL_NAME = "gpt-4o-mini"


class LlmConfigurationError(ValueError):
    """Raised when a caller has not supplied enough LLM configuration."""

    def __init__(self, message: str, *, code: str = "LLM_CONFIG_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    api_base: str
    model_name: str
    source: Literal["product", "support_env", "test"] = "product"


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def resolve_product_llm_config(
    *,
    api_key: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig:
    key = _clean(api_key)
    if not key:
        raise LlmConfigurationError("请先在设置中配置 LLM API Key。", code="NO_LLM_KEY")
    return LlmConfig(
        api_key=key,
        api_base=_clean(api_base) or DEFAULT_LLM_API_BASE,
        model_name=_clean(model_name) or DEFAULT_LLM_MODEL_NAME,
        source="product",
    )


def resolve_product_llm_config_from_credential(
    *,
    llm_credential_id: str | None,
    api_base: str | None,
    model_name: str | None,
    credential_vault: CredentialVault | None = None,
) -> LlmConfig:
    """Resolve a product key from the OS-backed vault at the provider boundary."""
    if not _clean(llm_credential_id):
        raise LlmConfigurationError(
            "请先在设置中配置 LLM 凭据。",
            code="NO_LLM_CREDENTIAL",
        )
    vault = credential_vault or get_credential_vault()
    secret = vault.get(
        str(llm_credential_id),
        expected_kind=CredentialKind.LLM_API_KEY,
    )
    if not secret:
        raise DBFoxError(
            "LLM credential was not found.",
            code="LLM_CREDENTIAL_NOT_FOUND",
        )
    return resolve_product_llm_config(
        api_key=secret,
        api_base=api_base,
        model_name=model_name,
    )


def resolve_optional_product_llm_config(
    *,
    api_key: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig | None:
    if not _clean(api_key):
        return None
    return resolve_product_llm_config(
        api_key=api_key,
        api_base=api_base,
        model_name=model_name,
    )


def resolve_support_llm_config_from_env(
    *,
    require_key: bool = True,
    environ: Mapping[str, str] | None = None,
) -> LlmConfig:
    env = environ if environ is not None else os.environ
    key = _clean(env.get("OPENAI_API_KEY") or env.get("QWEN_API_KEY") or env.get("DBFOX_LLM_API_KEY"))
    if require_key and not key:
        raise LlmConfigurationError("LLM API key is required for support-mode LLM calls.", code="NO_LLM_KEY")
    base = _clean(env.get("OPENAI_API_BASE") or env.get("OPENAI_BASE_URL") or env.get("QWEN_API_BASE"))
    model = _clean(env.get("OPENAI_MODEL_NAME") or env.get("QWEN_MODEL_NAME"))
    return LlmConfig(
        api_key=key,
        api_base=base or DEFAULT_LLM_API_BASE,
        model_name=model or DEFAULT_LLM_MODEL_NAME,
        source="support_env",
    )
