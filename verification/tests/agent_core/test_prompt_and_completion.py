import pytest

from engine.agent.completion import (
    CompletionKind,
    CompletionPolicy,
    SemanticArtifactCompletionSupport,
    SemanticCitationConstraint,
)
from engine.agent.context import ContextObservation, ContextSnapshot, ResponseItemBatch
from engine.agent.context_budget import ContextBudgetExceeded, estimate_input_items_tokens
from engine.agent.definition import DEFAULT_AGENT_DEFINITION
from engine.agent.prompt import PromptAssembler
from engine.agent.turn import ModelTurnResult, TurnAssistantMessage, TurnTermination
from engine.resource import ResourceScopeRef


EVIDENCE_CAPABILITY = "verification.evidence"
METADATA_CAPABILITY = "verification.metadata"


def _policy() -> CompletionPolicy:
    return CompletionPolicy(
        constraints=(
            SemanticCitationConstraint(
                id="verification.citation",
                semantic_capability=EVIDENCE_CAPABILITY,
            ),
        ),
        supports=(
            SemanticArtifactCompletionSupport(
                id="verification.evidence",
                semantic_capability=EVIDENCE_CAPABILITY,
            ),
        ),
    )


def _context(*, observations=None, citable_artifact_ids=()):
    return ContextSnapshot(
        session_id="session-1",
        run_id="run-1",
        context_epoch=0,
        messages=[{"role": "user", "content": "分析订单趋势"}],
        observations=observations or [],
        citable_artifact_ids=list(citable_artifact_ids),
        sources=[],
        hash="context-hash",
    )


def _final(text: str) -> ModelTurnResult:
    return ModelTurnResult(
        messages=[TurnAssistantMessage(
            item_id="message:0",
            output_index=0,
            phase="final_answer",
            status="completed",
            text=text,
        )],
        termination=TurnTermination.COMPLETED,
    )


@pytest.mark.parametrize("status", ["failed", "rejected"])
@pytest.mark.parametrize("turn_count, expected", [(2, CompletionKind.REPAIR), (4, CompletionKind.FAIL)])
def test_unrecovered_capability_failure_cannot_be_cleared_by_prose_or_control(status, turn_count, expected):
    observations = [
        ContextObservation(id="failed", tool_name="capability", status=status,
                           summary="The operation did not succeed.", sequence=1),
        ContextObservation(id="control", tool_name="answer_control", function_kind="control",
                           status="succeeded", summary="Candidate received.", sequence=2,
                           contributes_progress=False, artifact_ids=["existing-source"]),
    ]
    policy = CompletionPolicy(constraints=(), supports=())
    decision = policy.evaluate(
        context=_context(observations=observations),
        model_result=_final("The operation is unavailable. Here is an explanation."),
        turn_count=turn_count, max_turns=4,
    )
    assert decision.kind is expected
    assert decision.missing == ["tool_recovery"]


def test_later_successful_capability_can_recover_a_failed_action():
    observations = [
        ContextObservation(id="failed", tool_name="capability", status="failed",
                           summary="Invalid request.", sequence=1),
        ContextObservation(id="recovered", tool_name="capability", status="succeeded",
                           summary="Corrected operation succeeded.", sequence=2),
    ]
    policy = CompletionPolicy(constraints=(), supports=())
    decision = policy.evaluate(context=_context(observations=observations),
                               model_result=_final("The corrected operation succeeded."),
                               turn_count=3, max_turns=4)
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_success_on_a_different_resource_does_not_recover_the_failed_action():
    observations = [
        ContextObservation(
            id="failed", tool_name="capability", status="failed", summary="Failed.", sequence=1,
            resource_refs=(ResourceScopeRef(kind="verification.source", id="first", version=1),),
        ),
        ContextObservation(
            id="unrelated", tool_name="capability", status="succeeded", summary="Read.", sequence=2,
            resource_refs=(ResourceScopeRef(kind="verification.source", id="second", version=1),),
        ),
    ]
    decision = _policy().evaluate(
        context=_context(observations=observations), model_result=_final("All actions succeeded."),
        turn_count=3, max_turns=8,
    )
    assert decision.kind is CompletionKind.REPAIR
    assert decision.missing == ["tool_recovery"]


def test_prompt_keeps_user_context_out_of_system_role():
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
    assert bundle.version == "5.5"
    assert "requested outcome, explicit constraints" in bundle.system_prompt
    assert "denominator" not in bundle.system_prompt
    assert "authorized Resource" in bundle.system_prompt
    assert "Prior assistant text and prior Artifact metadata are context" in bundle.system_prompt
    assert "use an available capability tool to re-observe it" in bundle.system_prompt
    assert "{{artifact:artifact_abc123}}" in bundle.system_prompt
    assert "{{cite:artifact_abc123}}" in bundle.system_prompt
    assert "Artifact embedding controls answer composition only" in bundle.system_prompt


def test_prompt_isolates_the_only_active_request_from_prior_history():
    context = ContextSnapshot(
        session_id="session-1",
        run_id="run-2",
        context_epoch=0,
        current_request="分析当前工作项",
        messages=[{"role": "user", "content": "这个资源包含什么"}],
        sources=[],
        hash="context-hash",
    )
    messages = PromptAssembler().assemble(
        definition=DEFAULT_AGENT_DEFINITION,
        context=context,
    ).messages

    assert messages[-2] == {"role": "user", "content": "这个资源包含什么"}
    assert 'scope="only_active_request"' in messages[-1]["content"]
    assert "分析当前工作项" in messages[-1]["content"]
    assert "Earlier user messages are conversation history" in messages[-1]["content"]


def test_completion_feedback_stays_context_without_replacing_the_active_request_or_steering():
    answer = {"type": "message", "role": "assistant", "status": "completed",
              "content": [{"type": "output_text", "text": "There are 12 rows."}]}
    focus = {"kind": "continue", "missing": ["inline_evidence"],
             "reason": "Rewrite with {{cite:artifact_result}}."}
    context = _context().model_copy(update={
        "current_request": "Count the rows.", "run_focus": focus,
        "response_batches": [ResponseItemBatch(turn_id="previous", items=[answer])],
        "consumed_steers": ["Keep the answer brief."],
    })
    bundle = PromptAssembler().assemble(definition=DEFAULT_AGENT_DEFINITION, context=context)
    assert bundle.messages[-3] == answer
    feedback = bundle.messages[-2]
    assert feedback["role"] == "system"
    assert '<dbfox_runtime_feedback scope="active_run">' in feedback["content"]
    assert "{{cite:artifact_result}}" in feedback["content"]
    assert "whole replacement answer" in feedback["content"]
    assert "Keep the answer brief." in bundle.messages[-1]["content"]
    assert sum("Rewrite with" in str(item) for item in bundle.messages) == 1
    assert "{{cite:artifact_result}}" not in bundle.system_prompt
    assert bundle.budget["run_focus_tokens"] == estimate_input_items_tokens([feedback])
    assert bundle.budget["estimated_prompt_tokens"] == estimate_input_items_tokens(bundle.messages)
    assert context.response_batches[0].items == [answer]
    assert context.run_focus == focus


def test_runtime_requirements_do_not_become_the_latest_user_query():
    from engine.agent.answer_requirements import AnswerRequirements

    context = _context().model_copy(update={
        "current_request": "Create the requested project file.",
        "answer_requirements": AnswerRequirements(evidence="required"),
        "run_focus": {"kind": "repair", "reason": "Use the real observed sources."},
    })
    bundle = PromptAssembler().assemble(definition=DEFAULT_AGENT_DEFINITION, context=context)
    latest = next(item for item in reversed(bundle.messages) if item.get("role") == "user")
    assert "Create the requested project file." in latest["content"]
    assert "<dbfox_answer_requirements" not in latest["content"]
    assert "<dbfox_runtime_feedback" not in latest["content"]
    assert bundle.messages[-1]["role"] == "system"
    assert bundle.budget["answer_requirements_tokens"] > 0
    assert bundle.budget["run_focus_tokens"] > 0
    assert "Use the real observed sources." not in bundle.system_prompt


def test_completion_feedback_is_required_instead_of_silently_dropped(monkeypatch):
    monkeypatch.setattr("engine.agent.prompt.build_system_prompt", lambda: "Trusted runtime policy.")
    definition = DEFAULT_AGENT_DEFINITION.model_copy(update={
        "limits": DEFAULT_AGENT_DEFINITION.limits.model_copy(update={"max_prompt_tokens": 1024}),
    })
    context = _context().model_copy(update={"run_focus": {"reason": "x" * 6000}})
    with pytest.raises(ContextBudgetExceeded):
        PromptAssembler().assemble(definition=definition, context=context)


def test_prompt_budget_reserves_space_for_tool_schemas():
    tool_schemas = [{
        "type": "function",
        "function": {
            "name": f"tool_{index}",
            "description": "x" * 1_000,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "y" * 500}},
            },
        },
    } for index in range(4)]

    bundle = PromptAssembler().assemble(
        definition=DEFAULT_AGENT_DEFINITION,
        context=_context(),
        tool_schemas=tool_schemas,
    )

    assert bundle.budget["reserved_tokens"] > 0
    assert bundle.budget["tool_schema_count"] == len(tool_schemas)
    assert bundle.budget["estimated_prompt_tokens"] == (
        bundle.budget["message_tokens"] + bundle.budget["reserved_tokens"]
    )
    assert bundle.budget["estimated_prompt_tokens"] <= DEFAULT_AGENT_DEFINITION.limits.max_prompt_tokens


def test_text_answer_can_finish_without_keyword_classification():
    decision = _policy().evaluate(
        context=_context(),
        model_result=_final("你好，我是 DBFox。"),
        turn_count=1,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_metadata_observation_can_support_an_answer_without_evidence_artifact():
    metadata = ContextObservation(
        id="obs-metadata",
        tool_name="catalog_overview",
        status="succeeded",
        summary="Observed resource metadata.",
        capabilities=(METADATA_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[metadata]),
        model_result=_final("这个资源包含 50 个对象。"),
        turn_count=2,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_single_evidence_artifact_still_requires_explicit_inline_evidence():
    result = ContextObservation(
        id="obs-result",
        tool_name="data_preview",
        status="succeeded",
        summary="Previewed verified rows.",
        artifact_ids=["artifact_preview"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[result], citable_artifact_ids=["artifact_preview"]),
        model_result=_final("样例中包含 5 行。"),
        turn_count=2,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["inline_evidence"]
    assert "{{cite:artifact_preview}}" in decision.reason
    assert "embed does not satisfy" in decision.reason


def test_multiple_evidence_artifacts_still_require_explicit_inline_evidence():
    observations = [
        ContextObservation(
            id=f"obs-{index}",
            tool_name="data_preview",
            status="succeeded",
            summary="Previewed verified rows.",
            artifact_ids=[f"artifact_{index}"],
            capabilities=(EVIDENCE_CAPABILITY,),
        )
        for index in (1, 2)
    ]
    decision = _policy().evaluate(
        context=_context(observations=observations, citable_artifact_ids=["artifact_1", "artifact_2"]),
        model_result=_final("对比结果已经整理完成。"),
        turn_count=2,
        max_turns=8,
    )

    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["inline_evidence"]


def test_evidence_artifact_can_synthesize_with_observed_inline_evidence():
    observation = ContextObservation(
        id="obs-1",
        tool_name="verification_read",
        status="succeeded",
        summary="Returned 12 aggregated rows.",
        artifact_ids=["artifact_result"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[observation], citable_artifact_ids=["artifact_result"]),
        model_result=_final("订单呈上升趋势。{{cite:artifact_result}}"),
        turn_count=3,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


@pytest.mark.parametrize("answer", [
    "{{cite:artifact_result}}",
    " \n{{cite:artifact_result}}\n {{cite:artifact_result}} ",
    "[{{cite:artifact_result}}]",
    "**{{cite:artifact_result}}**。",
])
@pytest.mark.parametrize("at_budget", [False, True])
def test_citations_alone_cannot_complete_or_become_a_bounded_partial(answer, at_budget):
    context = _context(observations=[ContextObservation(
        id="obs-result", tool_name="verification_read", status="succeeded",
        summary="Returned 12 rows.", artifact_ids=["artifact_result"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )], citable_artifact_ids=["artifact_result"])
    decision = _policy().evaluate(
        context=context, model_result=_final(answer),
        turn_count=8 if at_budget else 3, max_turns=8,
    )
    assert decision.kind is (CompletionKind.FAIL if at_budget else CompletionKind.REPAIR)
    assert decision.missing == ["answer"]
    assert "complete answer" in decision.reason
    assert _policy().evaluate_bounded_partial(
        context=context, model_result=_final(answer), reason="Stopped without progress.",
    ).kind is CompletionKind.REPAIR


def test_observed_work_product_can_be_delivered_with_a_citation_without_prose():
    context = _context(observations=[ContextObservation(
        id="obs-result", tool_name="verification_read", status="succeeded",
        summary="Created a work product.", artifact_ids=["artifact_result"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )], citable_artifact_ids=["artifact_result"])
    decision = _policy().evaluate(
        context=context,
        model_result=_final("{{artifact:artifact_result}}\n\n{{cite:artifact_result}}"),
        turn_count=3, max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_lookup_can_use_a_cited_preview_without_forcing_another_tool():
    observation = ContextObservation(
        id="obs-preview",
        tool_name="data_preview",
        status="succeeded",
        summary="Previewed 5 redacted rows.",
        artifact_ids=["artifact_preview"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[observation], citable_artifact_ids=["artifact_preview"]),
        model_result=_final("样例中包含 5 行。{{cite:artifact_preview}}"),
        turn_count=2,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_resource_profile_can_support_an_answer_without_evidence_artifact():
    profile = ContextObservation(
        id="obs-profile",
        tool_name="catalog_overview",
        status="succeeded",
        summary="Verified resource profile.",
        capabilities=(METADATA_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[profile]),
        model_result=_final("这是已验证的项目资源。"),
        turn_count=1,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_task_rejects_fabricated_inline_evidence():
    observation = ContextObservation(
        id="obs-1", tool_name="verification_read", status="succeeded",
        summary="Returned one row.", artifact_ids=["artifact_real"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[observation]),
        model_result=_final("共有 42 条。{{cite:artifact_fake}}"),
        turn_count=3, max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["valid_inline_evidence"]


def test_observed_artifact_can_be_embedded_in_final_answer():
    observation = ContextObservation(
        id="obs-visualization",
        tool_name="visualization_create",
        status="succeeded",
        summary="Created a visual explanation.",
        artifact_ids=["artifact_visualization"],
        capabilities=(METADATA_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[observation], citable_artifact_ids=["artifact_visualization"]),
        model_result=_final(
            "趋势如下。\n\n{{artifact:artifact_visualization}}\n\n随后是结论。"
        ),
        turn_count=2,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


@pytest.mark.parametrize(
    "answer",
    [
        "正文内 {{artifact:artifact_visualization}} 不是独立块。",
        "{{artifact:artifact_visualization_???}}",
        "{{artifact:f6309cf059814aa19d9c7fae2b4ee821}}",
        "{{artifact:artifact_visualization}}\n\n{{artifact:artifact_visualization}}",
    ],
)
def test_invalid_artifact_embed_requests_a_repair(answer: str):
    observation = ContextObservation(
        id="obs-visualization",
        tool_name="visualization_create",
        status="succeeded",
        summary="Created a visual explanation.",
        artifact_ids=["artifact_visualization"],
        capabilities=(METADATA_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[observation]),
        model_result=_final(answer),
        turn_count=2,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["valid_artifact_embeds"]


def test_unobserved_artifact_embed_requests_a_repair():
    decision = _policy().evaluate(
        context=_context(),
        model_result=_final("{{artifact:artifact_fabricated}}"),
        turn_count=2,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["valid_artifact_embeds"]


@pytest.mark.parametrize(("text", "missing"), [
    ("Observed a result.{{cite:artifact_excluded}}", "valid_inline_evidence"),
    ("{{artifact:artifact_excluded}}", "valid_artifact_embeds"),
])
def test_an_observation_does_not_authorize_an_excluded_answer_source(text, missing):
    context = _context(observations=[ContextObservation(
        id="obs-excluded", tool_name="verification_read", status="succeeded",
        summary="Previously observed", artifact_ids=["artifact_excluded"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )])
    decision = _policy().evaluate(context=context, model_result=_final(text), turn_count=2, max_turns=8)
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == [missing]
    assert _policy().evaluate_bounded_partial(
        context=context, model_result=ModelTurnResult(), reason="Forced stop",
    ).kind is CompletionKind.FAIL


def test_task_rejects_malformed_placeholder_citation():
    observation = ContextObservation(
        id="obs-1", tool_name="catalog_overview", status="succeeded",
        summary="Observed four tables.", artifact_ids=[],
        capabilities=(METADATA_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[observation]),
        model_result=_final("共有 4 张表。{{cite:artifact_result_???}}"),
        turn_count=1, max_turns=8,
    )
    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["valid_inline_evidence"]


def test_malformed_citation_fails_closed_at_turn_budget():
    decision = _policy().evaluate(
        context=_context(),
        model_result=_final("答案。{{cite:artifact_unfinished"),
        turn_count=8, max_turns=8,
    )
    assert decision.kind is CompletionKind.FAIL
    assert decision.missing == ["valid_inline_evidence"]


def test_evidence_answer_does_not_require_a_separate_review_stage():
    result = ContextObservation(
        id="obs-result", tool_name="verification_read", status="succeeded",
        summary="Returned trend data.", artifact_ids=["artifact_trend"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[result], citable_artifact_ids=["artifact_trend"]),
        model_result=_final("订单持续增长。{{cite:artifact_trend}}"),
        turn_count=3, max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_last_allowed_turn_can_produce_a_valid_answer():
    result = ContextObservation(
        id="obs-result", tool_name="verification_read", status="succeeded",
        summary="Returned trend data.", artifact_ids=["artifact_trend"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )
    decision = _policy().evaluate(
        context=_context(observations=[result], citable_artifact_ids=["artifact_trend"]),
        model_result=_final("订单持续增长。{{cite:artifact_trend}}"),
        turn_count=8, max_turns=8,
    )
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_turn_budget_fails_without_an_answer_candidate():
    decision = _policy().evaluate(
        context=_context(),
        model_result=ModelTurnResult(),
        turn_count=8,
        max_turns=8,
    )
    assert decision.kind is CompletionKind.FAIL
    assert decision.missing == ["answer"]


def test_bounded_partial_accepts_settled_evidence_without_answer_text():
    result = ContextObservation(
        id="obs-result",
        tool_name="verification_read",
        status="succeeded",
        summary="Returned verified rows.",
        artifact_ids=["artifact_result"],
        capabilities=(EVIDENCE_CAPABILITY,),
    )

    decision = _policy().evaluate_bounded_partial(
        context=_context(observations=[result], citable_artifact_ids=["artifact_result"]),
        model_result=ModelTurnResult(),
        reason="bounded",
    )

    assert decision.kind is CompletionKind.PARTIAL
    assert decision.evidence_artifact_ids == []


def test_public_sources_allow_delivery_repair_without_domain_partial_support():
    from engine.agent.answer_requirements import AnswerRequirements
    from engine.agent.answer_submission import AnswerSubmission

    policy = CompletionPolicy(constraints=(), supports=())
    context = _context().model_copy(update={
        "answer_requirements": AnswerRequirements(evidence="when_observed"),
        "citable_artifact_ids": ["artifact_file"],
        "has_observed_public_artifacts": True,
    })
    missing_citation = _final("The file has been saved.")
    decision = policy.evaluate_bounded_partial(
        context=context, model_result=missing_citation, reason="no-progress boundary",
    )
    assert decision.kind is CompletionKind.REPAIR
    assert decision.missing == ["structured_evidence"]
    # Permission to repair neither publishes the draft nor changes completion.
    assert policy.evaluate(context=context, model_result=missing_citation,
                           turn_count=3, max_turns=8).kind is CompletionKind.REPAIR
    valid = ModelTurnResult(termination=TurnTermination.COMPLETED,
                           submitted_answer=AnswerSubmission(parts=[{
                               "text": "The file has been saved.", "citations": ["artifact_file"],
                           }]))
    assert policy.evaluate(context=context, model_result=valid,
                           turn_count=4, max_turns=8).kind is CompletionKind.SYNTHESIZE
    no_sources = context.model_copy(update={"citable_artifact_ids": []})
    assert policy.evaluate_bounded_partial(context=no_sources, model_result=missing_citation,
                                           reason="bounded").kind is CompletionKind.FAIL


def test_bounded_partial_rejects_unfinished_text_and_non_result_artifact():
    metadata = ContextObservation(
        id="obs-metadata",
        tool_name="verification_inspect",
        status="succeeded",
        summary="Observed metadata.",
        artifact_ids=["artifact_metadata"],
        capabilities=(METADATA_CAPABILITY,),
    )
    unfinished = ModelTurnResult(messages=[TurnAssistantMessage(
        item_id="message:0",
        output_index=0,
        phase=None,
        status="incomplete",
        text="partial text",
    )])

    decision = _policy().evaluate_bounded_partial(
        context=_context(observations=[metadata]),
        model_result=unfinished,
        reason="bounded",
    )

    assert decision.kind is CompletionKind.FAIL
    assert decision.missing == ["usable_partial_result"]


def test_commentary_without_tools_cannot_become_the_final_answer():
    decision = _policy().evaluate(
        context=_context(),
        model_result=ModelTurnResult(
            messages=[TurnAssistantMessage(
                item_id="message:0",
                output_index=0,
                phase="commentary",
                status="completed",
                text="我继续检查相关数据。",
            )],
            termination=TurnTermination.COMPLETED,
        ),
        turn_count=1,
        max_turns=8,
    )

    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["completed_answer"]


def test_completed_text_without_phase_is_an_answer_candidate():
    decision = _policy().evaluate(
        context=_context(),
        model_result=ModelTurnResult(
            messages=[TurnAssistantMessage(
                item_id="message:0",
                output_index=0,
                phase=None,
                status="completed",
                text="这是最终答案。",
            )],
            termination=TurnTermination.COMPLETED,
        ),
        turn_count=1,
        max_turns=8,
    )

    assert decision.kind is CompletionKind.SYNTHESIZE
    assert decision.missing == []


def test_text_without_phase_and_without_normal_finish_does_not_complete():
    decision = _policy().evaluate(
        context=_context(),
        model_result=ModelTurnResult(messages=[TurnAssistantMessage(
            item_id="message:0",
            output_index=0,
            phase=None,
            status="completed",
            text="尚未完整的回答",
        )]),
        turn_count=1,
        max_turns=8,
    )

    assert decision.kind is CompletionKind.CONTINUE
    assert decision.missing == ["completed_answer"]
