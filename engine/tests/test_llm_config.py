from __future__ import annotations

import pytest

from engine.errors import DBFoxError
from engine.llm.config import LlmConfigurationError, resolve_product_llm_config_from_credential
from engine.llm.factory import LlmCallOptions, create_chat_model
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


def test_product_config_is_resolved_only_from_a_vault_reference() -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret=" sk-product ")

    config = resolve_product_llm_config_from_credential(
        llm_credential_id=credential_id,
        api_base=" https://product.example/v1 ",
        model_name=" gpt-product ",
        credential_vault=vault,
    )

    assert config.api_key == "sk-product"
    assert config.api_base == "https://product.example/v1"
    assert config.model_name == "gpt-product"
    assert config.source == "product"


def test_product_config_requires_a_credential_reference() -> None:
    with pytest.raises(LlmConfigurationError) as exc_info:
        resolve_product_llm_config_from_credential(
            llm_credential_id=None,
            api_base=None,
            model_name=None,
            credential_vault=InMemoryCredentialVault(),
        )

    assert exc_info.value.code == "NO_LLM_CREDENTIAL"


def test_product_config_rejects_a_missing_or_wrong_vault_reference() -> None:
    vault = InMemoryCredentialVault()
    wrong_kind_id = vault.put(kind=CredentialKind.DATASOURCE_PASSWORD, secret="database-secret")

    with pytest.raises(DBFoxError) as exc_info:
        resolve_product_llm_config_from_credential(
            llm_credential_id=wrong_kind_id,
            api_base=None,
            model_name=None,
            credential_vault=vault,
        )

    assert exc_info.value.code == "LLM_CREDENTIAL_NOT_FOUND"


def test_create_chat_model_delegates_to_openai_provider(monkeypatch) -> None:
    import engine.llm.factory as factory

    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="sk-product")
    config = resolve_product_llm_config_from_credential(
        llm_credential_id=credential_id,
        api_base="https://product.example/v1",
        model_name="gpt-product",
        credential_vault=vault,
    )
    captured: dict[str, object] = {}

    def fake_create_openai_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)

    create_chat_model(
        config,
        LlmCallOptions(temperature=0.2, max_tokens=123, timeout=9.0),
    )

    assert captured == {
        "model_name": "gpt-product",
        "api_key": "sk-product",
        "api_base": "https://product.example/v1",
        "temperature": 0.2,
        "max_tokens": 123,
        "timeout": 9.0,
    }
