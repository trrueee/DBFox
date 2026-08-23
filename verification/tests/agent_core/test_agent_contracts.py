from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine.agent.artifact import Artifact, ArtifactSelectionSuggestion, ArtifactType
from engine.agent.evidence import Evidence
from engine.agent.response import (
    AnswerCandidate,
    CompletionDisposition,
    CompletionLimitationCode,
    ResponseComposer,
    ResponseCompositionError,
)
from engine.agent.turn import (
    TurnStreamAssembler,
    TurnStreamError,
    TurnStreamItem,
    TurnStreamKind,
    TurnTermination,
)


def test_turn_stream_assembler_merges_reasoning_summary_and_fragmented_tool_call() -> None:
    result = TurnStreamAssembler().consume(
        [
            TurnStreamItem(
                kind=TurnStreamKind.REASONING_SUMMARY_START,
                item_id="reasoning",
                revision=1,
            ),
            TurnStreamItem(
                kind=TurnStreamKind.REASONING_SUMMARY_DELTA,
                item_id="reasoning",
                revision=2,
                content="分析中",
            ),
            TurnStreamItem(
                kind=TurnStreamKind.REASONING_SUMMARY_END,
                item_id="reasoning",
                revision=3,
            ),
            TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_START,
                item_id="tool:0",
                revision=1,
                tool_call_index=0,
                tool_call_id="call_1",
                tool_name="verification_read",
            ),
            TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_DELTA,
                item_id="tool:0",
                revision=2,
                tool_call_index=0,
                arguments_delta='{"sql":"SELECT ',
            ),
            TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_END,
                item_id="tool:0",
                revision=3,
                tool_call_index=0,
                arguments_delta='1"}',
            ),
            TurnStreamItem(
                kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
                item_id="tool:0",
                revision=4,
                output_index=0,
                model_output_item={
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "verification_read",
                    "arguments": '{"sql":"SELECT 1"}',
                },
            ),
            TurnStreamItem(
                kind=TurnStreamKind.FINISH,
                item_id="finish",
                revision=1,
                termination=TurnTermination.COMPLETED,
            ),
        ]
    )

    assert result.answer_text == ""
    assert result.reasoning_summary == "分析中"
    assert result.tool_calls[0].name == "verification_read"
    assert result.tool_calls[0].arguments == {"sql": "SELECT 1"}
    assert result.termination is TurnTermination.COMPLETED


def test_turn_stream_assembler_rejects_gaps_and_bad_tool_json() -> None:
    with pytest.raises(TurnStreamError, match="stream gap"):
        TurnStreamAssembler().consume(
            [TurnStreamItem(
                kind=TurnStreamKind.ANSWER_START,
                item_id="answer",
                revision=2,
            )]
        )

    with pytest.raises(TurnStreamError, match="invalid JSON"):
        TurnStreamAssembler().consume(
            [
                TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_START,
                    item_id="tool:0",
                    revision=1,
                    tool_call_index=0,
                    tool_call_id="call_1",
                    tool_name="verification_validate",
                    arguments_delta="{",
                ),
                TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_END,
                    item_id="tool:0",
                    revision=2,
                    tool_call_index=0,
                ),
            ]
        )


@pytest.mark.parametrize(
    ("termination", "error_code"),
    [
        (TurnTermination.INCOMPLETE, "MODEL_PROVIDER_INCOMPLETE"),
        (TurnTermination.FAILED, "MODEL_PROVIDER_FAILED"),
        (TurnTermination.CANCELLED, "MODEL_PROVIDER_CANCELLED"),
    ],
)
def test_turn_stream_assembler_rejects_non_completed_termination(
    termination: TurnTermination,
    error_code: str,
) -> None:
    with pytest.raises(TurnStreamError) as exc_info:
        TurnStreamAssembler().consume([
            TurnStreamItem(
                kind=TurnStreamKind.FINISH,
                item_id="finish",
                revision=1,
                termination=termination,
            )
        ])

    assert exc_info.value.code == error_code


def test_turn_stream_item_rejects_unknown_termination() -> None:
    with pytest.raises(ValueError):
        TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination="tool_calls",  # type: ignore[arg-type]
        )


def _artifact(artifact_id: str = "artifact_result_1") -> Artifact:
    return Artifact(
        id=artifact_id,
        session_id="session_1",
        run_id="run_1",
        type=ArtifactType.MARKDOWN,
        title="Verified work product",
        payload={"content": "42"},
    )


def test_response_composer_accepts_only_real_artifact_ids() -> None:
    artifact = _artifact()
    answer = AnswerCandidate(
        text="共有 42 条记录。",
        evidence=[
            Evidence(
                id="evidence_1",
                session_id="session_1",
                run_id="run_1",
                claim_id="claim_1",
                artifact_id=artifact.id,
                label="查询结果",
                observed_at=datetime.now(UTC),
                value=42,
            )
        ],
    )

    response = ResponseComposer().compose(
        session_id="session_1",
        run_id="run_1",
        completion_disposition=CompletionDisposition.COMPLETE,
        limitation_codes=[],
        answer=answer,
        artifacts=[artifact],
        selection_suggestion=ArtifactSelectionSuggestion(
            artifact_id=artifact.id,
            reason="最新查询结果",
        ),
    )

    assert response.referenced_artifact_ids == [artifact.id]
    assert response.completion_disposition is CompletionDisposition.COMPLETE
    assert response.limitation_codes == []


def test_bounded_partial_response_requires_machine_readable_limitations() -> None:
    response = ResponseComposer().compose(
        session_id="session_1",
        run_id="run_1",
        completion_disposition=CompletionDisposition.BOUNDED_PARTIAL,
        limitation_codes=[CompletionLimitationCode.TURN_BUDGET_REACHED],
        answer=AnswerCandidate(text="这是当前可验证的结果。"),
        artifacts=[],
    )

    assert response.completion_disposition is CompletionDisposition.BOUNDED_PARTIAL
    assert response.limitation_codes == [CompletionLimitationCode.TURN_BUDGET_REACHED]

    with pytest.raises(ValueError, match="require at least one limitation code"):
        ResponseComposer().compose(
            session_id="session_1",
            run_id="run_1",
            completion_disposition=CompletionDisposition.BOUNDED_PARTIAL,
            limitation_codes=[],
            answer=AnswerCandidate(text="结果受限。"),
            artifacts=[],
        )


def test_response_composer_never_falls_back_to_semantic_identity() -> None:
    artifact = _artifact()
    answer = AnswerCandidate(
        text="共有 42 条记录。",
        evidence=[
            Evidence(
                id="evidence_1",
                session_id="session_1",
                run_id="run_1",
                claim_id="claim_1",
                artifact_id="result_view",
                label="查询结果",
                observed_at=datetime.now(UTC),
            )
        ],
    )

    with pytest.raises(ResponseCompositionError, match="unknown Artifact ID"):
        ResponseComposer().compose(
            session_id="session_1",
            run_id="run_1",
            completion_disposition=CompletionDisposition.COMPLETE,
            limitation_codes=[],
            answer=answer,
            artifacts=[artifact],
        )
