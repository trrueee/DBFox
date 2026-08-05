"""Opt-in contract check against a real OpenAI-compatible Responses provider."""

from __future__ import annotations

import os
import json

import pytest

from engine.agent.completion import CompletionKind, CompletionPolicy
from engine.agent.context import ContextSnapshot
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.turn import TurnStreamAssembler, TurnTermination
from engine.llm.config import (
    DEFAULT_LLM_API_BASE,
    DEFAULT_LLM_MODEL_NAME,
    LlmConfig,
    resolve_product_llm_config_from_credential,
)
from engine.llm.endpoint_policy import normalize_llm_api_base


def _real_provider_config() -> LlmConfig:
    credential_id = os.getenv("DBFOX_REAL_LLM_CREDENTIAL_ID", "").strip()
    api_base = os.getenv("DBFOX_REAL_LLM_API_BASE")
    model_name = os.getenv("DBFOX_REAL_LLM_MODEL")
    if credential_id:
        return resolve_product_llm_config_from_credential(
            llm_credential_id=credential_id,
            api_base=api_base,
            model_name=model_name,
        )
    api_key = os.getenv("DBFOX_REAL_LLM_API_KEY", "").strip()
    if api_key and os.getenv("DBFOX_ALLOW_REAL_LLM_ENV_KEY") == "1":
        return LlmConfig(
            api_key=api_key,
            api_base=normalize_llm_api_base(api_base or DEFAULT_LLM_API_BASE),
            model_name=(model_name or DEFAULT_LLM_MODEL_NAME).strip(),
            source="test",
        )
    pytest.skip(
        "Set an OS-vault DBFOX_REAL_LLM_CREDENTIAL_ID, or explicitly enable the test-only CI key gate"
    )


@pytest.mark.integration
@pytest.mark.real_llm
def test_real_responses_provider_completes_provider_neutral_text_contract() -> None:
    config = _real_provider_config()
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


@pytest.mark.integration
@pytest.mark.real_llm
def test_real_responses_provider_closes_function_call_loop() -> None:
    adapter = OpenAIModelAdapter.from_config(_real_provider_config())
    user_message = {
        "role": "user",
        "content": (
            "Call get_dbfox_contract_fixture exactly once with key='dbfox'. "
            "After the tool output arrives, answer with the returned integer value."
        ),
    }
    tools = [
        {
            "type": "function",
            "name": "get_dbfox_contract_fixture",
            "description": "Return the deterministic integer fixture for this contract test.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "enum": ["dbfox"]}},
                "required": ["key"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    first = TurnStreamAssembler().consume(
        adapter.stream(messages=[user_message], tools=tools, timeout_seconds=60)
    )
    assert first.termination is TurnTermination.COMPLETED
    assert len(first.tool_calls) == 1
    call = first.tool_calls[0]
    assert call.name == "get_dbfox_contract_fixture"
    assert call.arguments == {"key": "dbfox"}

    tool_output = {
        "type": "function_call_output",
        "call_id": call.id,
        "output": json.dumps({"value": 7}),
    }
    second = TurnStreamAssembler().consume(
        adapter.stream(
            messages=[user_message, *first.output_items, tool_output],
            tools=tools,
            timeout_seconds=60,
        )
    )
    assert second.termination is TurnTermination.COMPLETED
    assert second.tool_calls == []
    assert second.answer_text
    assert "7" in second.answer_text
