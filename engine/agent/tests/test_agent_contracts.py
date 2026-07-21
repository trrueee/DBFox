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
from engine.agent.turn import TurnStreamAssembler, TurnStreamError, TurnStreamItem, TurnStreamKind


def test_turn_stream_assembler_merges_text_and_fragmented_tool_call() -> None:
    result = TurnStreamAssembler().consume(
        [
            TurnStreamItem(kind=TurnStreamKind.TEXT_DELTA, channel="text", offset=0, content="分析"),
            TurnStreamItem(kind=TurnStreamKind.TEXT_DELTA, channel="text", offset=1, content="中"),
            TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_START,
                channel="tool:0",
                offset=0,
                tool_call_index=0,
                tool_call_id="call_1",
                tool_name="sql.execute_readonly",
            ),
            TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_DELTA,
                channel="tool:0",
                offset=1,
                tool_call_index=0,
                arguments_delta='{"sql":"SELECT ',
            ),
            TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_END,
                channel="tool:0",
                offset=2,
                tool_call_index=0,
                arguments_delta='1"}',
            ),
            TurnStreamItem(
                kind=TurnStreamKind.FINISH,
                channel="meta",
                offset=0,
                finish_signal="tool_calls",
            ),
        ]
    )

    assert result.text == "分析中"
    assert result.tool_calls[0].name == "sql.execute_readonly"
    assert result.tool_calls[0].arguments == {"sql": "SELECT 1"}
    assert result.finish_signal == "tool_calls"


def test_turn_stream_assembler_rejects_gaps_and_bad_tool_json() -> None:
    with pytest.raises(TurnStreamError, match="stream gap"):
        TurnStreamAssembler().consume(
            [TurnStreamItem(kind=TurnStreamKind.TEXT_DELTA, channel="text", offset=1, content="x")]
        )

    with pytest.raises(TurnStreamError, match="invalid JSON"):
        TurnStreamAssembler().consume(
            [
                TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_START,
                    channel="tool:0",
                    offset=0,
                    tool_call_index=0,
                    tool_call_id="call_1",
                    tool_name="sql.validate",
                    arguments_delta="{",
                )
            ]
        )


def _artifact(artifact_id: str = "artifact_result_1") -> Artifact:
    return Artifact(
        id=artifact_id,
        session_id="session_1",
        run_id="run_1",
        type=ArtifactType.RESULT_VIEW,
        title="查询结果",
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
                query_fingerprint="fingerprint_1",
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
                query_fingerprint="fingerprint_1",
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
