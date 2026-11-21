"""The untrusted answer boundary is domain-neutral and does not grant success."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.agent.answer_submission import AnswerSubmission
from engine.agent.turn import ModelTurnResult, ModelToolCall, TurnTermination


def test_submission_preserves_markdown_and_explicit_claim_boundaries():
    answer = AnswerSubmission.model_validate({"parts": [
        {"text": "## Findings\n\n**Count: 12.**", "citations": ["artifact_one"]},
        {"text": "\n\n| Check | Outcome |\n|---|---|\n| tests | passed |\n"},
        {"text": "The file is ready.", "citations": ["artifact_two", "artifact_one"]},
    ]})
    assert answer.text == (
        "## Findings\n\n**Count: 12.**{{cite:artifact_one}}"
        "\n\n| Check | Outcome |\n|---|---|\n| tests | passed |\n"
        "The file is ready.{{cite:artifact_two}}{{cite:artifact_one}}"
    )
    assert answer.citation_claims == ["## Findings\n\n**Count: 12.**", "The file is ready.", "The file is ready."]
    assert answer.cited_artifact_ids == {"artifact_one", "artifact_two"}


@pytest.mark.parametrize("value", [
    {"parts": []},
    {"parts": [{"text": " "}]},
    {"parts": [{"text": " ", "citations": ["artifact_one"]}]},
    {"parts": [{"text": "Only {{cite:artifact_one}}"}]},
    {"parts": [{"text": "Answer", "citations": ["artifact_one", "artifact_one"]}]},
    {"parts": [{"text": "Answer", "citations": ["evidence_one"]}]},
    {"parts": [{"text": "Answer", "citations": ["artifact_bad???"]}]},
    {"parts": [{"text": "Answer", "citations": ["artifact_one"], "observed_at": "now"}]},
    {"parts": [{"text": "Answer"}], "success": True},
    {"parts": [{"text": "Answer"}], "evidence": []},
    {"parts": [{"text": "Answer"}], "run_id": "another-run"},
    {"parts": [{"text": "a" * 16_001}, {"text": "b" * 16_000}]},
])
def test_submission_rejects_invalid_or_authority_bearing_input(value):
    with pytest.raises(ValidationError):
        AnswerSubmission.model_validate(value)


@pytest.mark.parametrize("termination", list(TurnTermination))
def test_submission_cannot_promote_a_failed_or_pending_provider_turn(termination):
    answer = AnswerSubmission.model_validate({"parts": [{"text": "Explanation."}]})
    result = ModelTurnResult(submitted_answer=answer, termination=termination)
    assert result.has_completed_answer_candidate is (termination is TurnTermination.COMPLETED)
    pending = result.model_copy(update={"tool_calls": [ModelToolCall(id="pending", name="work", arguments={})]})
    assert not pending.has_completed_answer_candidate
    assert not result.messages  # No invented native assistant message.
