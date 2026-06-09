from __future__ import annotations

import json

from engine.agent_kernel.intent_classifier import classify_intent_ai_first
from engine.agent_kernel.lifecycle import (
    classify_intent,
    classify_intent_fallback,
    plan_route,
    reflect,
    resolve_context,
    resolve_reference,
    understand_node,
)
from engine.agent_kernel.graph import build_agent_kernel_graph, langgraph_available


def test_lifecycle_classifies_sql_revision_from_existing_context() -> None:
    state = {
        "messages": [{"role": "user", "content": "把刚才的 SQL 改成按月统计"}],
        "workspace_context": {"active_sql": "SELECT DATE(created_at), total FROM orders"},
        "execute": False,
    }

    assert classify_intent(state) == "revise_sql"
    route = plan_route({**state, "agent_intent": {"intent": "revise_sql"}})
    assert route["route"] == ["sql.revise", "sql.validate", "answer.synthesize"]
    assert route["next_focus"] == "sql.revise"
    assert route["reference"]["kind"] == "sql"
    assert route["is_review_only"] is True


def test_lifecycle_context_and_reflection_are_structured() -> None:
    state = {
        "datasource_id": "ds-1",
        "messages": [{"role": "user", "content": "查一下 GMV"}],
        "sql": "SELECT SUM(total_amount) FROM orders",
        "safety": {"can_execute": False, "blocked_reasons": ["unknown_column"]},
        "artifacts": [{"id": "sql_candidate"}],
    }

    context = resolve_context(state)
    reflection = reflect(state)

    assert context["datasource_id"] == "ds-1"
    assert context["has_sql"] is True
    assert context["has_safety"] is True
    assert context["artifact_count"] == 1
    assert context["resolved_reference"]["kind"] == "sql"
    assert reflection["safety_blocked"] is True


def test_lifecycle_resolves_latest_sql_artifact_for_pronoun_reference() -> None:
    state = {
        "messages": [{"role": "user", "content": "解释一下刚才那个"}],
        "artifacts": [
            {
                "id": "art_result",
                "semantic_id": "result_table",
                "type": "table",
                "payload": {"columns": ["city", "gmv"], "rowCount": 10},
            },
            {
                "id": "art_sql",
                "semantic_id": "sql_candidate",
                "type": "sql",
                "payload": {"sql": "SELECT city, SUM(gmv) FROM orders GROUP BY city"},
            },
        ],
    }

    reference = resolve_reference(state)
    context = resolve_context(state)

    assert reference["kind"] == "sql"
    assert reference["source"] == "artifact"
    assert reference["id"] == "art_sql"
    assert context["has_selected_sql"] is True
    assert classify_intent(state) == "explain_sql"


def test_lifecycle_resolves_workspace_approval_for_risk_question() -> None:
    state = {
        "messages": [{"role": "user", "content": "这个为什么要审批？"}],
        "workspace_context": {"pending_approval_id": "appr-1"},
    }

    reference = resolve_reference(state)
    route = plan_route({**state, "agent_intent": {"intent": "approval_help", "reference": reference}})

    assert reference["kind"] == "approval"
    assert route["next_focus"] == "answer.synthesize"
    assert classify_intent(state) == "approval_help"


def test_agent_kernel_graph_exposes_lifecycle_nodes() -> None:
    if not langgraph_available():
        return

    graph = build_agent_kernel_graph(
        controller_node=lambda _state: {"pending_decision": {"action": "final_answer"}, "status": "completed"},
        policy_node=lambda _state: {},
        execute_tool_node=lambda _state: {},
    )

    assert graph is not None


# ---------------------------------------------------------------------------
# AI-first intent classifier tests
# ---------------------------------------------------------------------------


def test_classify_intent_backward_compat_alias() -> None:
    """classify_intent is still importable and delegates to classify_intent_fallback."""
    state = {
        "messages": [{"role": "user", "content": "把刚才的 SQL 改成按月统计"}],
        "workspace_context": {"active_sql": "SELECT DATE(created_at), total FROM orders"},
    }
    assert classify_intent(state) == "revise_sql"
    assert classify_intent(state) == classify_intent_fallback(state)


def test_ai_first_falls_back_when_no_api_key() -> None:
    """When state has no api_key, returns rule_fallback source and llm_trace=None."""
    state = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback)
    assert intent == "new_data_question"
    assert source == "rule_fallback"
    assert llm_trace is None


def test_ai_first_falls_back_when_api_key_is_empty_string() -> None:
    state = {
        "messages": [{"role": "user", "content": "解释这个 SQL"}],
        "api_key": "",
        "sql": "SELECT * FROM orders",
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback)
    assert intent == "explain_sql"
    assert source == "rule_fallback"
    assert llm_trace is None


def test_ai_first_uses_llm_when_api_key_present(monkeypatch) -> None:
    """With a valid api_key the LLM path is used and returns source='llm'."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "revise_sql",
                                "confidence": "high",
                                "reason": "The user is asking to modify the SQL.",
                                "needs_execution": False,
                            })
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state = {
        "messages": [{"role": "user", "content": "把刚才的 SQL 改成按月统计"}],
        "sql": "SELECT * FROM orders",
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback, api_key="sk-test")
    assert intent == "revise_sql"
    assert source == "llm"
    assert llm_trace is not None
    assert "llm_candidate" in llm_trace


def test_ai_first_falls_back_when_llm_confidence_is_low(monkeypatch) -> None:
    """LLM returns confidence=low → fallback with llm_trace containing fallback_reason."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "new_data_question",
                                "confidence": "low",
                                "reason": "Unclear what the user wants.",
                                "needs_execution": False,
                            })
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback, api_key="sk-test")
    assert intent == "new_data_question"
    assert source == "rule_fallback"
    assert llm_trace is not None
    assert llm_trace["fallback_reason"] == "llm_low_confidence"
    assert llm_trace["llm_candidate"]["confidence"] == "low"


def test_ai_first_falls_back_when_llm_returns_invalid_intent(monkeypatch) -> None:
    """LLM returns an intent not in VALID_INTENTS → fallback with trace."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "drop_table",
                                "confidence": "high",
                                "reason": "User wants to drop a table.",
                                "needs_execution": True,
                            })
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state = {
        "messages": [{"role": "user", "content": "删掉 users 表"}],
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback, api_key="sk-test")
    assert intent in {
        "new_data_question",
        "followup_on_result",
        "explain_sql",
        "revise_sql",
        "approval_help",
        "chart_request",
        "clarification",
    }
    assert source == "rule_fallback"
    assert llm_trace is not None
    assert llm_trace["fallback_reason"] == "llm_invalid_intent"


def test_ai_first_falls_back_when_llm_returns_malformed_json(monkeypatch) -> None:
    """LLM returns unparseable text → fallback with llm_trace=None."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "not valid json at all"}}]}

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
        "api_key": "sk-test",
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback)
    assert intent == "new_data_question"
    assert source == "rule_fallback"
    assert llm_trace is None


def test_ai_first_falls_back_when_httpx_raises(monkeypatch) -> None:
    """Network/HTTP error → fallback with llm_trace=None."""

    def _raise(*_args, **_kwargs):
        raise OSError("Connection refused")

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", _raise)

    state = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
        "api_key": "sk-test",
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback)
    assert intent == "new_data_question"
    assert source == "rule_fallback"
    assert llm_trace is None


def test_understand_node_includes_source_field() -> None:
    """understand_node output always includes the 'source' key."""
    state: dict = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
    }
    result = understand_node(state)
    payload = result["agent_intent"]
    assert "source" in payload
    assert payload["source"] in {"llm", "rule_fallback"}


def test_understand_node_source_is_rule_fallback_without_api_key() -> None:
    """Without api_key, understand_node sets source='rule_fallback'."""
    state: dict = {
        "messages": [{"role": "user", "content": "解释一下这个 SQL"}],
        "sql": "SELECT * FROM orders",
    }
    result = understand_node(state)
    assert result["agent_intent"]["source"] == "rule_fallback"
    assert result["agent_intent"]["intent"] == "explain_sql"


def test_understand_node_includes_llm_trace_when_llm_rejected(monkeypatch) -> None:
    """When LLM returns low confidence, understand_node records llm_trace."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "new_data_question",
                                "confidence": "low",
                                "reason": "Unsure about the request.",
                                "needs_execution": False,
                            })
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state: dict = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
    }
    result = understand_node(state, config={"configurable": {"api_key": "sk-test"}})
    payload = result["agent_intent"]
    assert payload["source"] == "rule_fallback"
    assert "llm_trace" in payload
    assert payload["llm_trace"]["fallback_reason"] == "llm_low_confidence"


def test_ai_first_llm_json_inside_markdown_fence(monkeypatch) -> None:
    """LLM response wrapped in ```json fence is still parsed correctly."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"intent": "chart_request", "confidence": "high", "reason": "User wants a chart.", "needs_execution": false}\n```'
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state = {
        "messages": [{"role": "user", "content": "画个柱状图"}],
        "execution": {"success": True},
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback, api_key="sk-test")
    assert intent == "chart_request"
    assert source == "llm"
    assert llm_trace is not None


def test_clarification_trusted_even_at_low_confidence(monkeypatch) -> None:
    """LLM returns clarification with low confidence → trusted, not fallen back.

    Falling back would risk reclassifying the message as new_data_question
    and starting an unwanted SQL pipeline.  Clarification is the safe intent.
    """

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "clarification",
                                "confidence": "low",
                                "reason": "The user's message is too vague.",
                                "needs_execution": False,
                            })
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state = {
        "messages": [{"role": "user", "content": "嗯..."}],
    }
    intent, source, llm_trace = classify_intent_ai_first(state, fallback=classify_intent_fallback, api_key="sk-test")
    assert intent == "clarification"
    assert source == "llm"
    assert llm_trace is not None


def test_trace_event_includes_source_and_llm_trace(monkeypatch) -> None:
    """The agent.understand trace event payload carries source + llm_trace."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "intent": "new_data_question",
                                "confidence": "low",
                                "reason": "Unclear.",
                                "needs_execution": False,
                            })
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state: dict = {
        "messages": [{"role": "user", "content": "查一下 GMV"}],
    }
    result = understand_node(state, config={"configurable": {"api_key": "sk-test"}})
    trace_events = result.get("trace_events", [])
    assert len(trace_events) == 1
    trace_payload = trace_events[0]["payload"]
    assert trace_payload["source"] == "rule_fallback"
    assert "llm_trace" in trace_payload
    assert trace_payload["llm_trace"]["fallback_reason"] == "llm_low_confidence"
