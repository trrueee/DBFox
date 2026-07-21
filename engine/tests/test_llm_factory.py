from __future__ import annotations

from types import SimpleNamespace

from engine.llm.config import LlmConfig
from engine.llm.factory import create_openai_compatible_client


def test_factory_uses_the_provider_neutral_openai_compatible_boundary(monkeypatch):
    captured: dict[str, object] = {}
    client = object()

    def create(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr("engine.llm.factory.create_openai_compatible_api_client", create)
    config = LlmConfig(
        api_key="secret", api_base="https://example.test/v1", model_name="model",
    )
    assert create_openai_compatible_client(config, timeout=12.0) is client
    assert captured == {
        "api_key": "secret", "api_base": "https://example.test/v1", "timeout": 12.0,
    }


def test_provider_disables_sdk_retries_and_owns_transport(monkeypatch):
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        "engine.llm.providers.openai.resolve_runtime_llm_endpoint",
        lambda value: SimpleNamespace(api_base=value),
    )
    transport = object()
    monkeypatch.setattr(
        "engine.llm.providers.openai.get_llm_http_clients",
        lambda **_kwargs: (transport, object()),
    )
    from engine.llm.providers.openai import create_openai_compatible_api_client

    create_openai_compatible_api_client(
        api_key="secret", api_base="https://example.test/v1", timeout=12.0,
    )
    assert captured["max_retries"] == 0
    assert captured["http_client"] is transport
