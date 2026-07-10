"""LLM configuration resolution boundaries."""
from __future__ import annotations

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
    source: Literal["product", "test"] = "product"


@dataclass(frozen=True)
class LlmConnectionPreferences:
    """Opaque LLM request preferences safe to persist or forward internally."""

    api_base: str
    model_name: str


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _resolved_product_llm_config(
    *,
    vault_secret: str,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig:
    """Build the internal config after the vault has supplied the secret."""
    return LlmConfig(
        api_key=vault_secret,
        api_base=_clean(api_base) or DEFAULT_LLM_API_BASE,
        model_name=_clean(model_name) or DEFAULT_LLM_MODEL_NAME,
        source="product",
    )


def normalize_product_llm_preferences(
    *,
    llm_credential_id: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConnectionPreferences:
    """Validate an opaque credential reference without resolving its secret."""
    if not _clean(llm_credential_id):
        raise LlmConfigurationError(
            "请先在设置中配置 LLM 凭据。",
            code="NO_LLM_CREDENTIAL",
        )
    return LlmConnectionPreferences(
        api_base=_clean(api_base) or DEFAULT_LLM_API_BASE,
        model_name=_clean(model_name) or DEFAULT_LLM_MODEL_NAME,
    )


def resolve_product_llm_config_from_credential(
    *,
    llm_credential_id: str | None,
    api_base: str | None,
    model_name: str | None,
    credential_vault: CredentialVault | None = None,
) -> LlmConfig:
    """Resolve a product key from the OS-backed vault at the provider boundary."""
    preferences = normalize_product_llm_preferences(
        llm_credential_id=llm_credential_id,
        api_base=api_base,
        model_name=model_name,
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
    return _resolved_product_llm_config(
        vault_secret=secret,
        api_base=preferences.api_base,
        model_name=preferences.model_name,
    )
