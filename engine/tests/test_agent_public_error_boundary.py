from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

import engine.api.agent as agent_api
from engine.agent.app.response_builder import build_response
from engine.agent.app.service import _runtime_error_message
from engine.agent.graph.context import GraphRuntimeContext
import engine.agent.nodes.model_node as model_node
import engine.agent.nodes.progress_node as progress_node
import engine.agent.progress.llm_judge as llm_judge
from engine.agent_core.types import AgentRunRequest
from engine.models import AgentRuntimeEventRecord
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


def _isolated_caplog_logger(
    caplog: pytest.LogCaptureFixture,
    *,
    name: str,
    level: int = logging.ERROR,
) -> logging.Logger:
    logger = logging.Logger(name)
    logger.setLevel(level)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    return logger


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


def test_model_node_converts_provider_invoke_failures_before_returning_state(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingModel:
        def bind_tools(self, _tools: object) -> object:
            return self

        def invoke(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError(SENTINEL)

    class FailingRuntime:
        registry = object()
        has_llm_credentials = True

        def create_chat_model(self) -> object:
            return FailingModel()

    monkeypatch.setattr(model_node, "graph_context", lambda _config: FailingRuntime())
    monkeypatch.setattr(model_node, "build_langchain_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(model_node, "_build_escalate_tool", lambda _registry: None)

    result = model_node.call_model({"step_count": 0, "max_steps": 2}, {})

    assert result["status"] == "failed"
    assert result["error"] == "The agent run could not be completed."
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


def test_model_node_contains_failures_before_the_main_model_try_block(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_grace_check(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(model_node, "_within_post_query_analysis_grace", fail_grace_check)

    result = model_node.call_model({"step_count": 1, "max_steps": 1}, {})

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


def test_progress_judge_converts_provider_invoke_failures_before_returning_state(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingStructuredModel:
        def with_structured_output(self, _schema: object) -> object:
            return self

        def invoke(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError(SENTINEL)

    class FailingRuntime:
        def create_chat_model(self) -> object:
            return FailingStructuredModel()

    monkeypatch.setattr(llm_judge, "graph_context", lambda _config: FailingRuntime())

    result = llm_judge.call_llm_judge({"messages": [], "step_count": 0, "max_steps": 2}, {})

    assert result["progress_decision"]["status"] == "continue"
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


def test_llm_judge_contains_failures_while_building_the_judgment_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_runtime_lookup(_config: object) -> object:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(llm_judge, "graph_context", fail_runtime_lookup)

    result = llm_judge.call_llm_judge({"messages": [], "step_count": 0, "max_steps": 2}, {})

    assert result["status"] == "failed"
    assert result["error"] == "The agent run could not be completed."
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


@pytest.mark.real_llm
def test_progress_node_contains_provider_failures_from_the_judge(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Runtime:
        has_llm_credentials = True

    def fail_provider(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(progress_node, "graph_context", lambda _config: Runtime())
    monkeypatch.setattr(progress_node, "check_escalate", lambda _state: None)
    monkeypatch.setattr(progress_node, "check_sql_repair_fastpath", lambda _state: None)
    monkeypatch.setattr(progress_node, "deterministic_progress_fastpath", lambda _state: None)
    monkeypatch.setattr(progress_node, "call_llm_judge", fail_provider)

    result = progress_node.judge_progress({"messages": [], "step_count": 0, "max_steps": 2}, {})

    assert result["status"] == "failed"
    assert result["error"] == "The agent run could not be completed."
    assert SENTINEL not in repr(result)
    assert SENTINEL not in caplog.text


@pytest.mark.real_llm
def test_service_graph_never_persists_a_judge_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    db_session: object,
    test_datasource: object,
    tmp_path: object,
) -> None:
    """The real Service/StateGraph path must contain failures before SQLite writes them."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    import engine.agent.app.service as service_module

    checkpoint_path = tmp_path / "agent-checkpoints.sqlite"

    def empty_model_response(
        state: dict[str, object],
        config: RunnableConfig,
    ) -> dict[str, object]:
        del config
        return {
            "messages": [AIMessage(content="")],
            "step_count": int(state.get("step_count", 0)) + 1,
        }

    def fail_provider(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(model_node, "call_model", empty_model_response)
    monkeypatch.setattr(progress_node, "call_llm_judge", fail_provider)
    capture_logger = _isolated_caplog_logger(
        caplog,
        name="test.agent_public_error_boundary.progress_node",
    )
    monkeypatch.setattr(progress_node, "logger", capture_logger)

    try:
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            checkpointer.setup()
            monkeypatch.setattr(service_module, "build_agent_core_checkpointer", lambda: checkpointer)
            service = service_module.DBFoxAgentService(db_session)
            events = list(
                service.run_iter(
                    AgentRunRequest(
                        datasource_id=test_datasource.id,
                        question="show orders",
                        session_id="checkpoint-sentinel-session",
                        conversation_id="checkpoint-sentinel-session",
                        llm_credential_id="cred_llm_api_key_checkpoint_test",
                        max_steps=2,
                    )
                )
            )
        public_events = "\n".join(event.model_dump_json() for event in events)
        persisted_events = "\n".join(
            row.event_json for row in db_session.query(AgentRuntimeEventRecord).all()
        )
        final_event = next(event for event in reversed(events) if event.response is not None)

        assert checkpoint_path.exists()
        assert final_event.response is not None
        assert final_event.response.error == "The agent run could not be completed."
        assert SENTINEL.encode() not in checkpoint_path.read_bytes()
        assert SENTINEL not in public_events
        assert SENTINEL not in persisted_events
        assert SENTINEL not in caplog.text
        assert "RuntimeError" in caplog.text
    finally:
        capture_logger.removeHandler(caplog.handler)


def test_workspace_context_failure_uses_a_fixed_catalog_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.agent_core.workspace_context as workspace_context
    from engine.agent_core.types import AgentWorkspaceContext

    class FailingSchemaLinker:
        def __init__(self, _db: object) -> None:
            pass

        def link(self, **_kwargs: object) -> object:
            raise RuntimeError(SENTINEL)

    monkeypatch.setattr(workspace_context, "SchemaLinker", FailingSchemaLinker)

    payload = workspace_context._schema_linking_payload(
        object(),
        _request(),
        AgentWorkspaceContext(datasource_id="ds-1"),
        [],
    )

    assert payload["error_code"] == "AGENT_CONTEXT_UNAVAILABLE"
    assert payload["error"] == "Agent context is temporarily unavailable."
    assert SENTINEL not in repr(payload)


def test_semantic_parse_failure_uses_a_fixed_catalog_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.agent_core.sql_semantic_verifier as verifier

    def fail_parse(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(verifier.sqlglot, "parse_one", fail_parse)

    violations = verifier.verify_sql_against_contract("SELECT 1", object(), {})

    assert violations[0].code == "sql_parse_failed"
    assert violations[0].message == "SQL could not be parsed."
    assert SENTINEL not in repr(violations[0].to_dict())


def test_response_builder_discards_nested_graph_error_text() -> None:
    response = build_response(
        req=_request(),
        run_id="run-response-boundary",
        session_id="session-response-boundary",
        state={
            "status": "failed",
            "error": SENTINEL,
            "progress_decision": {
                "status": "failed",
                "root_cause": SENTINEL,
            },
            "trace_events": [
                {
                    "type": "agent.tool.completed",
                    "tool_name": "db.preview",
                    "status": "failed",
                    "error": SENTINEL,
                }
            ],
        },
        success=False,
        error=SENTINEL,
        status="failed",
    )

    assert response.error == "The agent run could not be completed."
    assert SENTINEL not in response.model_dump_json()


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
