from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from engine.agent.app.request_context import RequestContext
from engine.agent.graph.context import graph_context
from engine.agent_core.types import AgentRunRequest
from engine.security.credential_vault import CredentialKind, InMemoryCredentialVault
from engine.tools.runtime.registry import ToolRegistry


def test_graph_config_contains_only_opaque_credential_reference() -> None:
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret="sk-phase1-reference")
    request = AgentRunRequest(
        datasource_id="ds-1",
        question="show orders",
        llm_credential_id=credential_id,
    )
    context = RequestContext(
        cast(Session, object()),
        request,
        registry=cast(ToolRegistry, object()),
        credential_vault=vault,
    )

    config = context.graph_config("run-1")

    assert config["configurable"]["llm_credential_id"] == credential_id
    assert set(config["configurable"]) == {
        "thread_id",
        "run_id",
        "runtime_id",
        "llm_credential_id",
    }
    assert "api_key" not in config["configurable"]
    assert "request" not in config["configurable"]


def test_sentinel_secret_never_appears_in_serialized_graph_config() -> None:
    sentinel = "sk-phase1-config-sentinel"
    vault = InMemoryCredentialVault()
    credential_id = vault.put(kind=CredentialKind.LLM_API_KEY, secret=sentinel)
    request = AgentRunRequest(
        datasource_id="ds-1",
        question="show orders",
        llm_credential_id=credential_id,
    )
    context = RequestContext(
        cast(Session, object()),
        request,
        registry=cast(ToolRegistry, object()),
        credential_vault=vault,
    )

    config = context.graph_config("run-1")

    assert sentinel not in repr(config)
    resolved = graph_context(config)
    assert resolved.request is request
    assert resolved.llm_credential_id == credential_id
    assert not hasattr(resolved, "api_key")
    assert resolved.has_llm_credentials is True
