"""Deterministic completion policy for the dynamic Agent loop."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.context import ContextSnapshot
from engine.agent.evidence import citation_references, has_invalid_citation_syntax
from engine.agent.turn import ModelTurnResult
from engine.tools.runtime.semantics import ToolSemanticCapability


class CompletionKind(StrEnum):
    CONTINUE = "continue"
    REPAIR = "repair"
    ASK_USER = "ask_user"
    SYNTHESIZE = "synthesize"
    PARTIAL = "partial"
    FAIL = "fail"


class CompletionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CompletionKind
    reason: str
    missing: list[str] = Field(default_factory=list)
    evidence_artifact_ids: list[str] = Field(default_factory=list)


class CompletionPolicy:
    """Provider output is advisory; durable observations decide completion."""

    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        turn_count: int,
        max_turns: int,
    ) -> CompletionDecision:
        if model_result.tool_calls:
            return CompletionDecision(
                kind=CompletionKind.CONTINUE,
                reason="The model requested tools that must be settled before completion.",
            )

        successes = [item for item in context.observations if item.status == "succeeded"]
        failures = [item for item in context.observations if item.status == "failed"]
        result_observations = [
            item for item in successes
            if ToolSemanticCapability.QUERY_RESULT.value in item.capabilities
        ]
        result_artifact_ids = {
            artifact_id
            for observation in result_observations
            for artifact_id in observation.artifact_ids
        }
        cited_artifact_ids = {
            artifact_id
            for artifact_id, _, _ in citation_references(model_result.answer_text)
        }

        turn_budget_reached = turn_count >= max_turns

        if failures and not model_result.display_text and not turn_budget_reached:
            return CompletionDecision(
                kind=CompletionKind.REPAIR,
                reason="The latest failed tool call needs a model-visible repair turn.",
            )

        if not model_result.display_text:
            return CompletionDecision(
                kind=CompletionKind.FAIL if turn_budget_reached else CompletionKind.CONTINUE,
                reason=(
                    "The run reached its turn budget without an answer candidate."
                    if turn_budget_reached
                    else "The model has not produced an answer candidate."
                ),
                missing=["answer"],
            )
        if not model_result.has_completed_answer_candidate:
            return CompletionDecision(
                kind=(
                    CompletionKind.FAIL
                    if turn_budget_reached
                    else CompletionKind.CONTINUE
                ),
                reason=(
                    "The model text is not a completed answer for the active request."
                ),
                missing=["completed_answer"],
            )

        if has_invalid_citation_syntax(model_result.answer_text):
            return CompletionDecision(
                kind=CompletionKind.FAIL if turn_budget_reached else CompletionKind.CONTINUE,
                reason=(
                    "The answer contains malformed or unresolved DBFox citation markup."
                ),
                missing=["valid_inline_evidence"],
            )

        observed_artifact_ids = {
            artifact_id
            for observation in successes
            for artifact_id in observation.artifact_ids
        }
        if cited_artifact_ids - observed_artifact_ids:
            return CompletionDecision(
                kind=CompletionKind.FAIL if turn_budget_reached else CompletionKind.CONTINUE,
                reason="The answer cites an Artifact that is not present in the durable observations.",
                missing=["valid_inline_evidence"],
            )

        supported_citations = cited_artifact_ids & result_artifact_ids
        if result_observations and not supported_citations and len(result_artifact_ids) != 1:
            return CompletionDecision(
                kind=CompletionKind.FAIL if turn_budget_reached else CompletionKind.CONTINUE,
                reason="An answer based on query results must cite an observed result Artifact inline.",
                missing=["inline_evidence"],
            )

        if turn_budget_reached:
            return CompletionDecision(
                kind=CompletionKind.PARTIAL,
                reason="The run reached its turn budget with an answer candidate.",
                evidence_artifact_ids=sorted(
                    supported_citations or (
                        result_artifact_ids if len(result_artifact_ids) == 1 else set()
                    )
                ),
            )

        return CompletionDecision(
            kind=CompletionKind.SYNTHESIZE,
            reason="The answer candidate is supported by the available durable observations.",
            evidence_artifact_ids=sorted(
                supported_citations or (
                    result_artifact_ids if len(result_artifact_ids) == 1 else set()
                )
            ),
        )

    def evaluate_bounded_partial(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        reason: str,
    ) -> CompletionDecision:
        """Decide whether a forced stop has durable, safe work to return.

        A completed answer candidate still passes the normal evidence and
        citation policy. Without an answer, only a settled query-result
        Artifact can support the generic bounded-partial response composed by
        Terminalizer. Arbitrary artifacts and interrupted text are not enough.
        """

        if model_result.has_completed_answer_candidate:
            decision = self.evaluate(
                context=context,
                model_result=model_result,
                turn_count=1,
                max_turns=1,
            )
            if decision.kind is CompletionKind.PARTIAL:
                return decision.model_copy(update={"reason": reason})
            return decision

        result_artifact_ids = [
            artifact_id
            for observation in context.observations
            if observation.status == "succeeded"
            and ToolSemanticCapability.QUERY_RESULT.value in observation.capabilities
            for artifact_id in observation.artifact_ids
        ]
        if result_artifact_ids:
            return CompletionDecision(
                kind=CompletionKind.PARTIAL,
                reason=reason,
                evidence_artifact_ids=[result_artifact_ids[-1]],
            )
        return CompletionDecision(
            kind=CompletionKind.FAIL,
            reason="The forced stop has no completed answer or durable query result.",
            missing=["usable_partial_result"],
        )


class CompletionGate:
    """Owns terminal eligibility independently from orchestration."""

    def __init__(self, policy: CompletionPolicy | None = None) -> None:
        self.policy = policy or CompletionPolicy()

    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        turn_count: int,
        max_turns: int,
    ) -> CompletionDecision:
        return self.policy.evaluate(
            context=context,
            model_result=model_result,
            turn_count=turn_count,
            max_turns=max_turns,
        )

    def evaluate_bounded_partial(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        reason: str,
    ) -> CompletionDecision:
        return self.policy.evaluate_bounded_partial(
            context=context,
            model_result=model_result,
            reason=reason,
        )
