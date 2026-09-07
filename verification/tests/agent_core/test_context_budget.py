import json

from engine.agent.context import (
    ContextObservation,
    ContextSnapshot,
    ResponseItemBatch,
)
from engine.agent.context_budget import estimate_messages_tokens


def test_responses_message_shorthand_uses_the_same_budget_as_explicit_messages() -> None:
    from engine.agent.context_budget import estimate_input_item_tokens, estimate_message_tokens

    for role in ("system", "developer", "user", "assistant"):
        message = {"role": role, "content": "JSON and 中文 context"}
        assert estimate_input_item_tokens(message) == estimate_input_item_tokens({"type": "message", **message})
        assert estimate_input_item_tokens(message) == estimate_message_tokens(message)


def test_deferred_schema_budget_counts_descriptions_and_loaded_history_in_full() -> None:
    from engine.agent.context_budget import estimate_input_item_tokens, estimate_tool_schema_tokens

    function = {"type": "function", "name": "inspect", "description": "inspect records",
                "parameters": {"type": "object", "description": "x" * 12_000}, "strict": True}
    deferred = {**function, "defer_loading": True}
    loaded = {"type": "tool_search_output", "execution": "server", "call_id": None,
              "status": "completed", "tools": [deferred]}
    assert estimate_tool_schema_tokens([deferred]) >= estimate_tool_schema_tokens([function])
    assert estimate_tool_schema_tokens([deferred, {"type": "tool_search"}]) < 100
    assert estimate_input_item_tokens(loaded) > 4_000
    assert estimate_tool_schema_tokens([
        {**deferred, "description": "x" * 12_000}, {"type": "tool_search"},
    ]) > 4_000


def test_prompt_preserves_native_search_order_and_evicts_its_complete_turn() -> None:
    from engine.agent.definition import AgentDefinition
    from engine.agent.prompt import PromptAssembler
    from engine.agent.run import RunLimits

    tools = [{"type": "function", "name": "inspect", "description": "Inspect",
              "parameters": {"type": "object", "properties": {}}, "defer_loading": True},
             {"type": "tool_search"}]
    items = [
        {"type": "tool_search_call", "execution": "server", "call_id": None,
         "status": "completed", "arguments": {"paths": ["inspect"]}},
        {"type": "tool_search_output", "execution": "server", "call_id": None,
         "status": "completed", "tools": [tools[0]]},
        {"type": "function_call", "call_id": "call_1", "name": "inspect", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "x" * 20_000},
    ]
    snapshot = ContextSnapshot(
        session_id="s", run_id="r", context_epoch=0, current_request="current request", messages=[],
        response_batches=[ResponseItemBatch(turn_id="t", items=items)], sources=[], hash="hash",
    )
    full = PromptAssembler().assemble(definition=AgentDefinition(), context=snapshot, tool_schemas=tools)
    assert full.messages[-4:] == items
    assert full.budget["response_item_tokens"] > 6_000
    reduced = PromptAssembler().assemble(
        definition=AgentDefinition(limits=RunLimits(max_prompt_tokens=4_096)),
        context=snapshot, tool_schemas=tools,
    )
    assert reduced.budget["omitted_response_batches"] == 1
    assert not any(item.get("type") in {"tool_search_call", "tool_search_output", "function_call", "function_call_output"}
                   for item in reduced.messages)
    assert reduced.budget["estimated_prompt_tokens"] <= 4_096
    assert snapshot.response_batches[0].items == items


def test_budget_keeps_current_request_and_drops_old_history_first() -> None:
    snapshot = ContextSnapshot(
        session_id="session-budget",
        run_id="run-budget",
        context_epoch=0,
        current_request="CURRENT REQUEST MUST SURVIVE",
        messages=[
            {"role": "user", "content": f"old-history-{index}-" + ("x" * 2_000)}
            for index in range(12)
        ],
        observations=[
            ContextObservation(
                id="latest-observation",
                tool_name="verification_read",
                status="succeeded",
                summary="verified",
                facts={"payload": "y" * 3_000},
            )
        ],
        run_focus={"missing": ["inline_evidence"]},
        sources=[],
        hash="budget-hash",
    )

    plan = snapshot.model_message_plan(
        system_prompt="trusted runtime policy",
        max_prompt_tokens=2_000,
    )
    encoded = "\n".join(str(item["content"]) for item in plan.messages)

    assert "CURRENT REQUEST MUST SURVIVE" in encoded
    assert "Deterministic completion guidance" in encoded
    assert estimate_messages_tokens(plan.messages) <= 2_000
    assert plan.omitted_messages > 0


def test_budget_accounts_for_typed_response_items_and_drops_complete_old_pairs() -> None:
    snapshot = ContextSnapshot(
        session_id="session",
        run_id="run",
        context_epoch=0,
        current_request="current",
        messages=[{"role": "user", "content": "old " + ("x" * 9_000)}],
        response_batches=[
            ResponseItemBatch(
                turn_id=f"turn-{index}",
                items=[
                    {
                        "type": "reasoning",
                        "encrypted_content": f"opaque-{index}",
                        "summary": [],
                    },
                    {
                        "type": "function_call",
                        "call_id": f"call-{index}",
                        "name": "result_inspect",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": f"call-{index}",
                        "output": "result-" + ("数" * 5_000),
                    },
                ],
            )
            for index in range(2)
        ],
        observations=[
            ContextObservation(
                id=f"observation-{index}",
                turn_id=f"turn-{index}",
                tool_name="verification_read",
                status="succeeded",
                summary=f"durable-result-{index}",
                artifact_ids=[f"artifact-result-{index}"],
                facts={"returned_rows": index + 1},
                capabilities=("verification.evidence",),
            )
            for index in range(2)
        ],
        sources=[],
        hash="hash",
    )
    from engine.agent.definition import AgentDefinition
    from engine.agent.prompt import PromptAssembler
    from engine.agent.run import RunLimits

    bundle = PromptAssembler().assemble(
        definition=AgentDefinition(limits=RunLimits(max_prompt_tokens=4_096)),
        context=snapshot,
    )

    encoded = json.dumps(bundle.messages, ensure_ascii=False)
    assert "current" in encoded
    assert "old " not in encoded
    assert bundle.budget["estimated_prompt_tokens"] <= 4_096
    assert bundle.budget["omitted_response_items"] > 0
    assert bundle.budget["omitted_response_batches"] > 0
    assert "durable_evidence_ledger" in encoded
    assert "artifact-result-0" in encoded
    retained_call_ids = {
        item["call_id"]
        for item in bundle.messages
        if item.get("type") == "function_call"
    }
    retained_output_ids = {
        item["call_id"]
        for item in bundle.messages
        if item.get("type") == "function_call_output"
    }
    assert retained_call_ids == retained_output_ids


def test_consumed_steer_follows_the_response_batch_it_updates() -> None:
    snapshot = ContextSnapshot(
        session_id="session",
        run_id="run",
        context_epoch=0,
        current_request="分析所有地区",
        consumed_steers=["只看华东区"],
        messages=[],
        response_batches=[
            ResponseItemBatch(
                turn_id="turn-1",
                items=[
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "all-regions-result",
                    }
                ],
            )
        ],
        sources=[],
        hash="hash",
    )
    from engine.agent.definition import AgentDefinition
    from engine.agent.prompt import PromptAssembler

    bundle = PromptAssembler().assemble(
        definition=AgentDefinition(),
        context=snapshot,
    )

    current_index = next(
        index
        for index, item in enumerate(bundle.messages)
        if "分析所有地区" in str(item.get("content") or "")
    )
    output_index = next(
        index
        for index, item in enumerate(bundle.messages)
        if item.get("type") == "function_call_output"
    )
    steer_index = next(
        index
        for index, item in enumerate(bundle.messages)
        if "只看华东区" in str(item.get("content") or "")
    )
    assert current_index < output_index < steer_index
    assert bundle.budget["consumed_steer_count"] == 1


def test_observations_are_internal_state_not_duplicate_model_messages() -> None:
    observations = [
        ContextObservation(
            id=f"observation-{index}",
            tool_name="db_search",
            status="succeeded",
            summary=("newest" if index == 5 else f"old-{index}") + ("x" * 1_400),
            sequence=index,
        )
        for index in range(6)
    ]
    snapshot = ContextSnapshot(
        session_id="session",
        run_id="run",
        context_epoch=0,
        current_request="current",
        messages=[],
        observations=observations,
        sources=[],
        hash="hash",
    )

    plan = snapshot.model_message_plan(
        system_prompt="system",
        max_prompt_tokens=1_024,
    )
    encoded = "\n".join(str(item["content"]) for item in plan.messages)

    assert "newest" not in encoded
    assert "old-0" not in encoded


def test_budget_truncates_only_request_payload_and_keeps_complete_envelope() -> None:
    snapshot = ContextSnapshot(
        session_id="session",
        run_id="run",
        context_epoch=0,
        current_request="中" * 5_000,
        messages=[],
        sources=[],
        hash="hash",
    )
    plan = snapshot.model_message_plan(
        system_prompt="system",
        max_prompt_tokens=1_024,
    )
    encoded = "\n".join(str(item["content"]) for item in plan.messages)

    assert "context truncated by runtime budget" in encoded
    assert "</dbfox_current_request>" in encoded


def test_workspace_context_is_sent_to_the_model_as_untrusted_context() -> None:
    snapshot = ContextSnapshot(
        session_id="session",
        run_id="run",
        context_epoch=0,
        current_request="解释当前编辑器里的查询",
        messages=[],
        workspace_context={
            "active_editor": "query.sql",
            "selected_text": "SELECT count(*) FROM orders",
        },
        sources=[],
        hash="hash",
    )

    plan = snapshot.model_message_plan(
        system_prompt="system",
        max_prompt_tokens=2_048,
    )
    encoded = "\n".join(str(item["content"]) for item in plan.messages)

    assert '<dbfox_context source="workspace_context">' in encoded
    assert "SELECT count(*) FROM orders" in encoded
    assert "SELECT count(*) FROM orders" not in plan.messages[0]["content"]
