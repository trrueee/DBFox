from engine.agent.completion import CompletionKind, CompletionPolicy, TaskKind
from engine.agent.context import ContextObservation, ContextSnapshot
from engine.agent.definition import DEFAULT_AGENT_DEFINITION
from engine.agent.prompt import PromptAssembler
from engine.agent.turn import ModelTurnResult


def _context(*, observations=None):
    return ContextSnapshot(
        session_id="session-1",
        run_id="run-1",
        context_epoch=0,
        messages=[{"role": "user", "content": "分析订单趋势"}],
        observations=observations or [],
        sources=[],
        hash="context-hash",
    )


def test_prompt_keeps_user_and_database_context_out_of_system_role():
    bundle = PromptAssembler().assemble(
        definition=DEFAULT_AGENT_DEFINITION,
        context=_context(),
    )
    assert bundle.messages[0]["role"] == "system"
    assert "分析订单趋势" not in bundle.messages[0]["content"]
    assert bundle.messages[-1] == {"role": "user", "content": "分析订单趋势"}
    assert bundle.hash == PromptAssembler().assemble(
        definition=DEFAULT_AGENT_DEFINITION,
        context=_context(),
    ).hash


def test_database_task_cannot_finish_on_provider_stop_without_result_evidence():
    decision = CompletionPolicy().evaluate(
        context=_context(),
        model_result=ModelTurnResult(text="订单增长了", finish_signal="stop"),
        task_kind=TaskKind.LOOKUP,
        turn_count=1,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert "verified_result" in decision.missing


def test_database_task_can_synthesize_after_readonly_observation():
    observation = ContextObservation(
        id="obs-1",
        tool_name="sql.execute_readonly",
        status="succeeded",
        summary="Returned 12 aggregated rows.",
        artifact_ids=["artifact_result"],
    )
    decision = CompletionPolicy().evaluate(
        context=_context(observations=[observation]),
        model_result=ModelTurnResult(text="订单呈上升趋势。{{cite:artifact_result}}", finish_signal="stop"),
        task_kind=TaskKind.LOOKUP,
        turn_count=3,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_database_task_rejects_fabricated_inline_evidence():
    observation = ContextObservation(
        id="obs-1", tool_name="sql.execute_readonly", status="succeeded",
        summary="Returned one row.", artifact_ids=["artifact_real"],
    )
    decision = CompletionPolicy().evaluate(
        context=_context(observations=[observation]),
        model_result=ModelTurnResult(text="共有 42 条。{{cite:artifact_fake}}", finish_signal="stop"),
        task_kind=TaskKind.LOOKUP, turn_count=3, max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["inline_evidence"]


def test_analytical_task_requires_dynamic_coverage_review():
    result = ContextObservation(
        id="obs-result", tool_name="sql.execute_readonly", status="succeeded",
        summary="Returned trend data.", artifact_ids=["artifact_trend"],
    )
    without_review = CompletionPolicy().evaluate(
        context=_context(observations=[result]),
        model_result=ModelTurnResult(text="订单持续增长。{{cite:artifact_trend}}", finish_signal="stop"),
        task_kind=TaskKind.ANALYTICAL, turn_count=3, max_turns=8,
    )
    assert without_review.missing == ["analysis_coverage_review"]

    review = ContextObservation(
        id="obs-review", tool_name="analysis.review", status="succeeded",
        summary="Coverage reviewed.", artifact_ids=[], facts={"ready": True},
    )
    with_review = CompletionPolicy().evaluate(
        context=_context(observations=[result, review]),
        model_result=ModelTurnResult(text="订单持续增长。{{cite:artifact_trend}}", finish_signal="stop"),
        task_kind=TaskKind.ANALYTICAL, turn_count=4, max_turns=8,
    )
    assert with_review.kind is CompletionKind.SYNTHESIZE
