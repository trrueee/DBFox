from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

import engine.api.agent as agent_api
from engine.agent.app.service import _runtime_error_message
from engine.agent.graph.context import GraphRuntimeContext
import engine.agent.nodes.model_node as model_node
import engine.agent.progress.llm_judge as llm_judge
from engine.agent_core.types import AgentRunRequest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault


SENTINEL = "provider-sentinel-not-a-redaction-pattern"


def _request() -> AgentRunRequest:
    return AgentRunRequest(
        datasource_id="ds-1",
        question="show orders",
        llm_credential_id="cred_llm_api_key_123",
    )


def _consume_stream(response: Any) -> str:
    async def consume() -> str:
        chunks: list[str] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else str(chunk))
        return "".join(chunks)

    return asyncio.run(consume())


def test_unknown_llm_exception_is_absent_from_all_public_agent_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeClient:
        def invoke(self, _prompt: str) -> None:
            raise RuntimeError(SENTINEL)

    config = SimpleNamespace(model_name="test-model", api_base="https://example.test/v1")
    monkeypatch.setattr(agent_api, "resolve_product_llm_config_from_credential", lambda **_kwargs: config)
    monkeypatch.setattr(agent_api, "create_chat_model", lambda *_args, **_kwargs: FakeClient())

    llm_test = agent_api.api_llm_test(
        agent_api.LlmTestRequest(
            llm_credential_id="cred_llm_api_key_123",
            api_base="https://example.test/v1",
            model_name="test-model",
        )
    )

    class FailingRuntime:
        def __init__(self, _db: object) -> None:
            pass

        def run(self, _req: AgentRunRequest) -> None:
            raise RuntimeError(SENTINEL)

        def run_iter(self, _req: AgentRunRequest):
            raise RuntimeError(SENTINEL)
            yield None

    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(agent_api, "_normalize_agent_run_llm_config", lambda req: req)
    monkeypatch.setattr(agent_api, "DBFoxAgentRuntime", FailingRuntime)

    with pytest.raises(HTTPException) as http_error:
        agent_api.api_agent_run(_request(), db)
    stream = _consume_stream(agent_api.api_agent_run_stream(_request(), db))
    state_error = _runtime_error_message(RuntimeError(SENTINEL))

    public_representations = [
        llm_test.model_dump_json(),
        repr(http_error.value.detail),
        stream,
        state_error,
    ]
    assert all(SENTINEL not in value for value in public_representations)
    assert llm_test.error_code == "LLM_TEST_FAILED"
    assert http_error.value.detail["code"] == "AGENT_RUNTIME_ERROR"
    assert "AGENT_RUNTIME_ERROR" in stream
    assert SENTINEL not in caplog.text


def test_graph_context_exposes_a_model_factory_not_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.agent.graph.context as graph_context_module

    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="sk-boundary-sentinel")
    captured: dict[str, object] = {}

    def fake_create_chat_model(config: object, _options: object | None = None) -> object:
        captured["config"] = config
        return object()

    monkeypatch.setattr(graph_context_module, "create_resolved_chat_model", fake_create_chat_model)
    context = GraphRuntimeContext(
        thread_id="thread-1",
        run_id="run-1",
        runtime_id="runtime-1",
        llm_credential_id=credential_id,
        registry=object(),
        db=object(),
        request=_request(),
        credential_vault=vault,
    )

    model = context.create_chat_model()

    assert model is not None
    assert not hasattr(context, "api_key")
    assert not hasattr(context, "llm_config")
    assert "sk-boundary-sentinel" not in repr(context.to_configurable())
    assert captured["config"].api_key == "sk-boundary-sentinel"


def test_model_node_converts_provider_failures_before_they_can_reach_a_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingRuntime:
        registry = object()
        has_llm_credentials = True

        def create_chat_model(self) -> object:
            raise RuntimeError(SENTINEL)

    monkeypatch.setattr(model_node, "graph_context", lambda _config: FailingRuntime())
    monkeypatch.setattr(model_node, "build_langchain_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(model_node, "_build_escalate_tool", lambda _registry: None)

    result = model_node.call_model({"step_count": 0, "max_steps": 2}, {})

    assert result["status"] == "failed"
    assert result["error"] == "The agent run could not be completed."
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


def test_progress_judge_converts_model_creation_failures_before_returning_state(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingRuntime:
        def create_chat_model(self) -> object:
            raise RuntimeError(SENTINEL)

    monkeypatch.setattr(llm_judge, "graph_context", lambda _config: FailingRuntime())

    result = llm_judge.call_llm_judge({"messages": [], "step_count": 0, "max_steps": 2}, {})

    assert result["progress_decision"]["status"] == "continue"
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


def test_agent_request_normalization_does_not_resolve_a_vault_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_api,
        "resolve_product_llm_config_from_credential",
        lambda **_kwargs: pytest.fail("request normalization must not resolve a vault secret"),
    )

    normalized = agent_api._normalize_agent_run_llm_config(_request())

    assert normalized.llm_credential_id == "cred_llm_api_key_123"
    assert normalized.api_base == "https://api.openai.com/v1"
    assert normalized.model_name == "gpt-4o-mini"


def test_raw_key_llm_adapters_are_not_public() -> None:
    import engine.llm as llm
    import engine.llm.config as config
    import engine.llm.factory as factory

    assert not hasattr(llm, "get_chat_model")
    assert not hasattr(factory, "get_chat_model")
    assert not hasattr(factory, "LLMClientFactory")
    assert not hasattr(config, "resolve_product_llm_config")
    assert not hasattr(config, "resolve_optional_product_llm_config")
    assert not hasattr(config, "resolve_support_llm_config_from_env")
