from __future__ import annotations

import asyncio
import socket
from types import SimpleNamespace
from typing import Any

import pytest

import engine.ai_index as ai_index
import engine.llm.providers.openai as openai_provider
from engine.llm.config import LlmConfig
from engine.llm.endpoint_policy import LlmEndpointPolicyError, ResolvedLlmEndpoint
from engine.llm.factory import create_openai_compatible_client
from engine.llm.http_clients import LlmHttpTransportRegistry


def _manual_config(api_base: str) -> LlmConfig:
    """A manually-built config must receive the same runtime safeguards."""

    return LlmConfig(
        api_key="TEST_LLM_SECRET",
        api_base=api_base,
        model_name="qwen-test",
    )


@pytest.mark.parametrize(
    "api_base",
    [
        "https://127.0.0.1/v1",
        "https://user:password@api.example.test/v1",
    ],
)
def test_schema_enrichment_rejects_unsafe_manual_endpoint_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    api_base: str,
) -> None:
    constructed = False

    class UnexpectedOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            nonlocal constructed
            constructed = True

    monkeypatch.setattr("openai.OpenAI", UnexpectedOpenAI)

    with pytest.raises(LlmEndpointPolicyError):
        ai_index._call_aliyun_llm("schema prompt", llm_config=_manual_config(api_base))

    assert constructed is False


def test_schema_enrichment_rejects_dns_rebinding_target_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = False

    class UnexpectedOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            nonlocal constructed
            constructed = True

    monkeypatch.setattr("openai.OpenAI", UnexpectedOpenAI)
    monkeypatch.setattr(
        "engine.llm.endpoint_policy.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ],
    )

    with pytest.raises(LlmEndpointPolicyError):
        ai_index._call_aliyun_llm(
            "schema prompt",
            llm_config=_manual_config("https://schema.example.test/v1"),
        )

    assert constructed is False


def test_schema_enrichment_delegates_to_the_shared_openai_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCompletions:
        def create(self, **kwargs: Any) -> Any:
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"tables": []}'))],
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    def fake_factory(config: LlmConfig, *, timeout: float) -> FakeClient:
        captured["config"] = config
        captured["timeout"] = timeout
        return FakeClient()

    monkeypatch.setattr(ai_index, "create_openai_compatible_client", fake_factory)

    result = ai_index._call_aliyun_llm(
        "schema prompt",
        llm_config=_manual_config("https://schema.example.test/v1"),
    )

    assert result == '{"tables": []}'
    assert captured["config"] == _manual_config("https://schema.example.test/v1")
    assert captured["timeout"] == ai_index.AI_ENRICH_LLM_TIMEOUT_SECONDS
    assert captured["request"] == {
        "model": "qwen-test",
        "messages": [{"role": "user", "content": "schema prompt"}],
        "temperature": 0.1,
        "max_tokens": 2048,
    }


def test_openai_compatible_factory_uses_owned_no_proxy_no_redirect_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    registry = LlmHttpTransportRegistry()

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        openai_provider,
        "resolve_runtime_llm_endpoint",
        lambda value: ResolvedLlmEndpoint(
            api_base=value,
            scheme="https",
            host="schema.example.test",
            port=443,
            addresses=("8.8.8.8",),
        ),
    )
    monkeypatch.setattr(openai_provider, "get_llm_http_clients", registry.get_clients)
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    try:
        create_openai_compatible_client(
            _manual_config("https://schema.example.test/v1"),
            timeout=12.0,
        )

        transport = captured["http_client"]
        assert captured["base_url"] == "https://schema.example.test/v1"
        assert captured["max_retries"] == 0
        assert transport.follow_redirects is False
        assert transport.trust_env is False
    finally:
        asyncio.run(registry.aclose())
