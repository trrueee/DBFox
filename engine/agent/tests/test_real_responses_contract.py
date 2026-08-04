"""Opt-in contract check against a real OpenAI-compatible Responses provider."""

from __future__ import annotations

import os

import pytest

from engine.agent.completion import CompletionKind, CompletionPolicy
from engine.agent.context import ContextSnapshot
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.turn import TurnStreamAssembler, TurnTermination
from engine.llm.config import resolve_product_llm_config_from_credential


@pytest.mark.integration
@pytest.mark.real_llm
def test_real_responses_provider_completes_provider_neutral_text_contract() -> None:
    credential_id = os.getenv("DBFOX_REAL_LLM_CREDENTIAL_ID", "").strip()
    if not credential_id:
        pytest.skip("Set DBFOX_REAL_LLM_CREDENTIAL_ID to an OS-vault credential to opt in")

    api_base = os.getenv("DBFOX_REAL_LLM_API_BASE")
    model_name = os.getenv("DBFOX_REAL_LLM_MODEL")
    config = resolve_product_llm_config_from_credential(
        llm_credential_id=credential_id,
        api_base=api_base,
        model_name=model_name,
    )
    result = TurnStreamAssembler().consume(OpenAIModelAdapter.from_config(config).stream(
        messages=[{
            "role": "user",
            "content": "Reply with one short sentence confirming this contract check completed.",
        }],
        tools=[],
        timeout_seconds=60,
    ))
    decision = CompletionPolicy().evaluate(
        context=ContextSnapshot(
            session_id="real-contract-session",
            run_id="real-contract-run",
            context_epoch=0,
            messages=[{"role": "user", "content": "Run the Responses contract check."}],
            observations=[],
            sources=[],
            hash="real-contract-context",
        ),
        model_result=result,
        turn_count=1,
        max_turns=1,
    )

    assert result.answer_text
    assert result.termination is TurnTermination.COMPLETED
    assert result.tool_calls == []
    assert result.has_completed_answer_candidate
    assert decision.kind in {CompletionKind.SYNTHESIZE, CompletionKind.PARTIAL}
