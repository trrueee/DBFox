import json

from engine.agent.context import (
    ContextObservation,
    ContextSnapshot,
    ResponseItemBatch,
)
from engine.agent.context_budget import estimate_messages_tokens


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
                tool_name="sql_execute_readonly",
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
                tool_name="sql_execute_readonly",
                status="succeeded",
                summary=f"durable-result-{index}",
                artifact_ids=[f"artifact-result-{index}"],
                facts={"returned_rows": index + 1},
                capabilities=("query_result",),
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
