from types import SimpleNamespace

import pytest
from openai import APIStatusError
from pydantic import ValidationError

import engine.api.agent as agent_module

def test_reusable_sql_memory_is_not_public_agent_api():
    route_paths = {getattr(route, "path", "") for route in agent_module.router.routes}

    assert "/agent/reusable-sqls" not in route_paths


def test_legacy_agent_run_surface_is_removed() -> None:
    retired_symbols = (
        "api_agent_run",
        "api_agent_run_resume",
        "api_agent_run_stream",
        "api_agent_run_resume_stream",
        "api_cancel_agent_run",
        "api_resolve_agent_approval",
        "api_get_agent_run",
    )
    assert all(not hasattr(agent_module, symbol) for symbol in retired_symbols)


def test_llm_test_uses_product_config_and_factory(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured["response"] = kwargs

    def fake_create_client(**kwargs):
        captured["client_kwargs"] = kwargs
        return SimpleNamespace(responses=FakeResponses())

    def fake_resolve_product_config(**kwargs):
        captured["resolve_kwargs"] = kwargs
        return SimpleNamespace(
            model_name="qwen-plus",
            api_key="test-secret",
            api_base="https://example.test/v1",
            source="product",
        )

    monkeypatch.setattr(
        agent_module,
        "resolve_product_llm_config_from_credential",
        fake_resolve_product_config,
    )
    monkeypatch.setattr(agent_module, "create_openai_responses_client", fake_create_client)

    response = agent_module.api_llm_test(
        agent_module.LlmTestRequest(
            llm_credential_id="cred_llm_api_key_test",
            api_base="https://example.test/v1",
            model_name="qwen-plus",
        )
    )

    resolve_kwargs = captured["resolve_kwargs"]
    assert response.ok is True
    assert response.model == "qwen-plus"
    assert response.api_base == "https://example.test/v1"
    assert captured["response"] == {
        "model": "qwen-plus",
        "input": "ping",
        "max_output_tokens": 16,
        "store": False,
    }
    assert captured["client_kwargs"] == {
        "api_key": "test-secret", "api_base": "https://example.test/v1", "timeout": 10.0,
    }
    assert resolve_kwargs == {
        "llm_credential_id": "cred_llm_api_key_test",
        "api_base": "https://example.test/v1",
        "model_name": "qwen-plus",
    }


def test_llm_test_falls_back_to_chat_completion_on_responses_404(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __init__(self, url: str) -> None:
            self.status_code = 404
            self.headers = {"x-request-id": "x-request-id"}
            self.request = SimpleNamespace(url=url)

    class FakeResponses:
        def create(self, **kwargs):
            captured["response"] = kwargs
            raise APIStatusError(
                message="Not Found",
                response=_FakeResponse("https://example.test/v1/responses"),
                body={"error": {"message": "not found"}},
            )

    class FakeChatCompletion:
        def create(self, **kwargs):
            captured["chat"] = kwargs

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeChatCompletion()

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()
            self.chat = FakeChat()

    def fake_create_client(**kwargs):
        captured["client_kwargs"] = kwargs
        return FakeClient()

    def fake_resolve_product_config(**kwargs):
        captured["resolve_kwargs"] = kwargs
        return SimpleNamespace(
            model_name="mimo-v2.5-pro",
            api_key="test-secret",
            api_base="https://example.test/v1",
            source="product",
        )

    monkeypatch.setattr(
        agent_module,
        "resolve_product_llm_config_from_credential",
        fake_resolve_product_config,
    )
    monkeypatch.setattr(agent_module, "create_openai_responses_client", fake_create_client)

    response = agent_module.api_llm_test(
        agent_module.LlmTestRequest(
            llm_credential_id="cred_llm_api_key_test",
            api_base="https://example.test/v1",
            model_name="mimo-v2.5-pro",
        )
    )

    resolve_kwargs = captured["resolve_kwargs"]
    assert response.ok is True
    assert response.model == "mimo-v2.5-pro"
    assert response.api_base == "https://example.test/v1"
    assert captured["response"] == {
        "model": "mimo-v2.5-pro",
        "input": "ping",
        "max_output_tokens": 16,
        "store": False,
    }
    assert captured["chat"] == {
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": "ping"}],
        "max_completion_tokens": 16,
    }
    assert captured["client_kwargs"] == {
        "api_key": "test-secret",
        "api_base": "https://example.test/v1",
        "timeout": 10.0,
    }
    assert resolve_kwargs == {
        "llm_credential_id": "cred_llm_api_key_test",
        "api_base": "https://example.test/v1",
        "model_name": "mimo-v2.5-pro",
    }


def test_llm_test_requires_opaque_credential_reference_even_when_env_exists(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "TEST_LLM_SECRET")

    with pytest.raises(ValidationError):
        agent_module.LlmTestRequest(
            api_base="https://example.test/v1",
            model_name="qwen-plus",
        )
