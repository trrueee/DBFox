from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_product_agent_run_requires_request_key_even_when_env_exists(monkeypatch) -> None:
    import engine.api.agent as agent_module
    from engine.agent_core.types import AgentRunRequest

    class FakeDb:
        def rollback(self) -> None:
            pass

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.delenv("DBFOX_TESTING", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_run(
            AgentRunRequest(datasource_id="ds-1", question="hello"),
            FakeDb(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "NO_LLM_KEY"


def test_graph_context_credentials_only_use_request_config(monkeypatch) -> None:
    from engine.agent.graph.context import GraphRuntimeContext

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    ctx = GraphRuntimeContext(
        thread_id="thread-1",
        registry=object(),  # type: ignore[arg-type]
        db=object(),  # type: ignore[arg-type]
        request=object(),  # type: ignore[arg-type]
        api_key=None,
    )

    assert ctx.has_llm_credentials is False
