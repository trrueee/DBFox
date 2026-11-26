"""Explicit provider selection is accepted at the HTTP contract boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.api.agent import LlmTestRequest
from engine.api.conversation_contracts import ConversationInputRequest
from engine.agent.loop import ProviderSettings
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentRun, AgentSession


def _input(**overrides: object) -> ConversationInputRequest:
    payload: dict[str, object] = {
        "content": "analyze revenue",
        "idempotency_key": "request-provider-1",
    }
    payload.update(overrides)
    return ConversationInputRequest(**payload)


def test_input_accepts_both_known_providers() -> None:
    assert _input(provider="openai-responses").provider == "openai-responses"
    assert _input(provider="openai-chat").provider == "openai-chat"


def test_input_defaults_to_no_provider_override() -> None:
    assert _input().provider is None


def test_input_rejects_an_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        _input(provider="anthropic-messages")


def test_llm_test_request_defaults_to_responses() -> None:
    request = LlmTestRequest(
        llm_credential_id="credential-1",
        api_base="https://api.openai.com/v1",
    )

    assert request.provider == "openai-responses"


def test_admitted_provider_reaches_the_run_settings(db_session) -> None:
    db_session.add(AgentSession(id="session-provider", title="Provider"))
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id="session-provider",
        resource_refs=(),
        content="query the source",
        idempotency_key="provider-contract-1",
        llm_credential_id="credential-1",
        api_base="https://api.deepseek.com/v1",
        model_name="deepseek-chat",
        request_payload={"provider": "openai-chat"},
    )
    db_session.commit()

    run = db_session.get(AgentRun, admission.run_id)

    assert run is not None
    assert ProviderSettings.from_run(run).provider == "openai-chat"
