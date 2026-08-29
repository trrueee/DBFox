"""Deterministic completion policy for the dynamic Agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.context import ContextSnapshot
from typing import Literal, Protocol

from engine.agent.artifact_embed import (
    MAX_ARTIFACT_EMBEDS,
    artifact_embed_ids,
    has_duplicate_artifact_embeds,
    has_invalid_artifact_embed_syntax,
)
from engine.agent.evidence import citation_references, has_invalid_citation_syntax
from engine.agent.turn import ModelTurnResult


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


class CompletionConstraintResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["pass", "missing", "veto"]
    reason: str
    requirements: list[str] = Field(default_factory=list)


class CompletionConstraint(Protocol):
    @property
    def id(self) -> str: ...

    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
    ) -> CompletionConstraintResult: ...


class CompletionSupport(Protocol):
    """Domain contribution for what counts as durable partial/evidence work.

    Core completion only composes the support decision; it never imports a
    concrete tool capability or Artifact family.
    """

    @property
    def id(self) -> str: ...

    def evidence_artifact_ids(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
    ) -> list[str]: ...

    def supports_bounded_partial(self, *, context: ContextSnapshot) -> bool: ...


@dataclass(frozen=True)
class SemanticCitationConstraint:
    """Require inline citation when a semantic observation family is present."""

    id: str
    semantic_capability: str
    requirement: str = "inline_evidence"

    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
    ) -> CompletionConstraintResult:
        observations = [
            item
            for item in context.observations
            if item.status == "succeeded"
            and self.semantic_capability in item.capabilities
        ]
        if not observations:
            return CompletionConstraintResult(
                kind="pass",
                reason="No matching observations require citation.",
            )
        artifact_ids = {
            artifact_id
            for observation in observations
            for artifact_id in observation.artifact_ids
        }
        cited = {
            artifact_id
            for artifact_id, _, _ in citation_references(model_result.answer_text)
        }
        if cited & artifact_ids:
            return CompletionConstraintResult(
                kind="pass",
                reason="The answer cites a matching observed Artifact.",
            )
        return CompletionConstraintResult(
            kind="missing",
            reason="An answer based on observed evidence must cite that Artifact inline.",
            requirements=[self.requirement],
        )


@dataclass(frozen=True)
class SemanticArtifactCompletionSupport:
    """Treat one semantic observation family as durable completion evidence."""

    id: str
    semantic_capability: str

    def evidence_artifact_ids(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
    ) -> list[str]:
        artifacts = {
            artifact_id
            for observation in context.observations
            if observation.status == "succeeded"
            and self.semantic_capability in observation.capabilities
            for artifact_id in observation.artifact_ids
        }
        cited = {
            artifact_id
            for artifact_id, _, _ in citation_references(model_result.answer_text)
        }
        return sorted(cited & artifacts)

    def supports_bounded_partial(self, *, context: ContextSnapshot) -> bool:
        return any(
            observation.status == "succeeded"
            and self.semantic_capability in observation.capabilities
            and bool(observation.artifact_ids)
            for observation in context.observations
        )


class CompletionPolicy:
    """Provider output is advisory; durable observations decide completion."""

    def __init__(
        self,
        constraints: tuple[CompletionConstraint, ...],
        supports: tuple[CompletionSupport, ...],
    ) -> None:
        self.constraints = constraints
        self.supports = supports

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
        result_artifact_ids = {
            artifact_id
            for support in self.supports
            for artifact_id in support.evidence_artifact_ids(
                context=context,
                model_result=model_result,
            )
        }
        cited_artifact_ids = {
            artifact_id
            for artifact_id, _, _ in citation_references(model_result.answer_text)
        }
        embedded_artifact_ids = artifact_embed_ids(model_result.answer_text)

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

        if (
            has_invalid_artifact_embed_syntax(model_result.answer_text)
            or has_duplicate_artifact_embeds(model_result.answer_text)
            or len(embedded_artifact_ids) > MAX_ARTIFACT_EMBEDS
        ):
            return CompletionDecision(
                kind=CompletionKind.FAIL if turn_budget_reached else CompletionKind.CONTINUE,
                reason=(
                    "The answer contains malformed, repeated, or excessive DBFox "
                    "Artifact embed markup."
                ),
                missing=["valid_artifact_embeds"],
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
        if set(embedded_artifact_ids) - observed_artifact_ids:
            return CompletionDecision(
                kind=CompletionKind.FAIL if turn_budget_reached else CompletionKind.CONTINUE,
                reason=(
                    "The answer embeds an Artifact that is not present in the durable "
                    "observations."
                ),
                missing=["valid_artifact_embeds"],
            )

        if turn_budget_reached:
            decision = CompletionDecision(
                kind=CompletionKind.PARTIAL,
                reason="The run reached its turn budget with an answer candidate.",
                evidence_artifact_ids=sorted(
                    cited_artifact_ids & result_artifact_ids
                ),
            )
        else:
            decision = CompletionDecision(
                kind=CompletionKind.SYNTHESIZE,
                reason="The answer candidate is supported by the available durable observations.",
                evidence_artifact_ids=sorted(
                    cited_artifact_ids & result_artifact_ids
                ),
            )
        return self._apply_constraints(
            decision,
            context=context,
            model_result=model_result,
            turn_count=turn_count,
            max_turns=max_turns,
        )

    def _apply_constraints(
        self,
        decision: CompletionDecision,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        turn_count: int,
        max_turns: int,
    ) -> CompletionDecision:
        """Compose immutable constraints after Core terminal eligibility.

        Any VETO wins; MISSING requirements are unioned and force another turn
        unless the budget is exhausted.
        """

        veto: CompletionConstraintResult | None = None
        missing: list[str] = []
        for constraint in self.constraints:
            result = constraint.evaluate(
                context=context,
                model_result=model_result,
            )
            if result.kind == "veto":
                veto = result
                break
            if result.kind == "missing":
                missing.extend(result.requirements)

        if veto is not None:
            return CompletionDecision(
                kind=(
                    CompletionKind.FAIL
                    if turn_count >= max_turns
                    else CompletionKind.CONTINUE
                ),
                reason=veto.reason,
                missing=list(dict.fromkeys(veto.requirements)),
                evidence_artifact_ids=[],
            )
        if missing:
            return CompletionDecision(
                kind=(
                    CompletionKind.FAIL
                    if turn_count >= max_turns
                    else CompletionKind.CONTINUE
                ),
                reason="Extension completion constraints require another model turn.",
                missing=list(dict.fromkeys(missing)),
                evidence_artifact_ids=[],
            )
        return decision

    def evaluate_bounded_partial(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        reason: str,
    ) -> CompletionDecision:
        """Decide whether a forced stop has durable, safe work to return.

        A completed answer candidate still passes the normal evidence and
        citation policy. Without an answer, only a capability support that has
        verified durable work can opt into the bounded-partial response
        composed by Terminalizer. Core never infers domain evidence from an
        Artifact payload.
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

        if any(
            support.supports_bounded_partial(context=context)
            for support in self.supports
        ):
            return CompletionDecision(
                kind=CompletionKind.PARTIAL,
                reason=reason,
                evidence_artifact_ids=[],
            )
        return CompletionDecision(
            kind=CompletionKind.FAIL,
            reason="The forced stop has no completed answer or supported durable work.",
            missing=["usable_partial_result"],
        )


class CompletionGate:
    """Owns terminal eligibility independently from orchestration."""

    def __init__(self, policy: CompletionPolicy) -> None:
        self.policy = policy

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
