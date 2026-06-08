from __future__ import annotations

from engine.agent_kernel.lifecycle import answer_node, critique_answer


def test_answer_critic_flags_data_claims_when_execution_is_skipped() -> None:
    state = {
        "execute": False,
        "execution": {"success": False, "reason": "skipped because execute=false"},
        "answer": {"answer": "The query returned 0 rows."},
    }

    critique = critique_answer(state)
    update = answer_node(state)

    assert critique["needs_correction"] is True
    assert critique["execution_skipped"] is True
    assert update["answer"]["answer"].endswith("I cannot make data-result claims.")
    assert update["final_answer"] == update["answer"]
    assert any(event["type"] == "agent.answer_critic" for event in update["trace_events"])


def test_answer_critic_passes_when_execution_evidence_exists() -> None:
    state = {
        "execution": {"success": True, "rowCount": 3, "columns": ["city", "gmv"]},
        "answer": {"answer": "The query returned 3 rows."},
    }

    critique = critique_answer(state)
    update = answer_node(state)

    assert critique["needs_correction"] is False
    assert "answer" not in update
    assert any(event["type"] == "agent.answer_critic" for event in update["trace_events"])
