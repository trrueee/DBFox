from __future__ import annotations

import os

import pytest


def test_product_resolver_ignores_environment(monkeypatch) -> None:
    from engine.llm.config import resolve_product_llm_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    config = resolve_product_llm_config(
        api_key=" sk-product ",
        api_base=" https://product.example/v1 ",
        model_name=" gpt-product ",
    )

    assert config.api_key == "sk-product"
    assert config.api_base == "https://product.example/v1"
    assert config.model_name == "gpt-product"
    assert config.source == "product"


def test_product_resolver_requires_request_api_key_even_when_env_exists(monkeypatch) -> None:
    from engine.llm.config import LlmConfigurationError, resolve_product_llm_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    with pytest.raises(LlmConfigurationError) as exc_info:
        resolve_product_llm_config(api_key=None, api_base=None, model_name=None)

    assert exc_info.value.code == "NO_LLM_KEY"


def test_optional_product_resolver_returns_none_without_key(monkeypatch) -> None:
    from engine.llm.config import resolve_optional_product_llm_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    assert resolve_optional_product_llm_config(
        api_key=None,
        api_base="https://product.example/v1",
        model_name="gpt-product",
    ) is None


def test_support_resolver_reads_env_aliases() -> None:
    from engine.llm.config import resolve_support_llm_config_from_env

    config = resolve_support_llm_config_from_env(environ={
        "QWEN_API_KEY": "sk-qwen",
        "QWEN_API_BASE": "https://dashscope.example/v1",
        "QWEN_MODEL_NAME": "qwen-plus",
    })

    assert config.api_key == "sk-qwen"
    assert config.api_base == "https://dashscope.example/v1"
    assert config.model_name == "qwen-plus"
    assert config.source == "support_env"


def test_support_resolver_prefers_openai_api_base_over_base_url() -> None:
    from engine.llm.config import resolve_support_llm_config_from_env

    config = resolve_support_llm_config_from_env(environ={
        "OPENAI_API_KEY": "sk-openai",
        "OPENAI_API_BASE": "https://api-base.example/v1",
        "OPENAI_BASE_URL": "https://base-url.example/v1",
    })

    assert config.api_base == "https://api-base.example/v1"


def test_create_chat_model_delegates_to_openai_provider(monkeypatch) -> None:
    from engine.llm.config import LlmConfig
    from engine.llm.factory import LlmCallOptions, create_chat_model
    import engine.llm.factory as factory

    captured: dict[str, object] = {}

    def fake_create_openai_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)

    create_chat_model(
        LlmConfig(
            api_key="sk-product",
            api_base="https://product.example/v1",
            model_name="gpt-product",
            source="product",
        ),
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


def test_get_chat_model_is_explicit_config_only(monkeypatch) -> None:
    import engine.llm.factory as factory

    captured: dict[str, object] = {}

    def fake_create_openai_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_API_BASE", "https://env.example/v1")
    monkeypatch.setenv("OPENAI_MODEL_NAME", "env-model")

    factory.get_chat_model(
        api_key="sk-product",
        api_base="https://product.example/v1",
        model_name="gpt-product",
    )

    assert captured["api_key"] == "sk-product"
    assert captured["api_base"] == "https://product.example/v1"
    assert captured["model_name"] == "gpt-product"


def test_support_env_resolution_has_no_global_test_side_effect(monkeypatch) -> None:
    from engine.llm.config import resolve_support_llm_config_from_env

    monkeypatch.setenv("QWEN_API_KEY", "sk-qwen")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = resolve_support_llm_config_from_env(environ={
        "QWEN_API_KEY": "sk-qwen",
        "QWEN_API_BASE": "https://dashscope.example/v1",
        "QWEN_MODEL_NAME": "qwen-plus",
    })

    assert config.api_key == "sk-qwen"
    assert os.environ.get("OPENAI_API_KEY") is None
