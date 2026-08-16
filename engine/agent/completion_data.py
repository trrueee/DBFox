"""Data-family Completion contribution.

Query-result citation and bounded-partial semantics live here instead of the
Completion Core. A future TestReport or Evaluation family contributes the same
two methods without editing ``completion.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.agent.completion import CompletionConstraintResult
from engine.agent.context import ContextSnapshot
from engine.agent.evidence import citation_references
from engine.agent.turn import ModelTurnResult
from engine.tools.runtime.semantics import ToolSemanticCapability


@dataclass(frozen=True)
class DataResultCitationConstraint:
    """Data-owned citation rule.

    A query-result answer must cite an observed result Artifact inline. The
    constraint can only add requirements; it cannot bypass pending work,
    approval, citation ownership or budget.
    """

    id: str = "dbfox.data.result_citation"

    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
    ) -> CompletionConstraintResult:
        result_observations = [
            item
            for item in context.observations
            if item.status == "succeeded"
            and ToolSemanticCapability.QUERY_RESULT.value in item.capabilities
        ]
        if not result_observations:
            return CompletionConstraintResult(
                kind="pass",
                reason="No query-result observations require citation.",
            )
        result_artifact_ids = {
            artifact_id
            for observation in result_observations
            for artifact_id in observation.artifact_ids
        }
        cited_artifact_ids = {
            artifact_id
            for artifact_id, _, _ in citation_references(model_result.answer_text)
        }
        supported = cited_artifact_ids & result_artifact_ids
        if supported:
            return CompletionConstraintResult(
                kind="pass",
                reason="The answer cites observed result Artifacts.",
            )
        return CompletionConstraintResult(
            kind="missing",
            reason=(
                "An answer based on query results must cite an observed "
                "result Artifact inline."
            ),
            requirements=["inline_evidence"],
        )


@dataclass(frozen=True)
class DataCompletionSupport:
    id: str = "dbfox.data.query_result"

    def evidence_artifact_ids(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
    ) -> list[str]:
        result_artifact_ids = {
            artifact_id
            for observation in context.observations
            if observation.status == "succeeded"
            and ToolSemanticCapability.QUERY_RESULT.value in observation.capabilities
            for artifact_id in observation.artifact_ids
        }
        cited_artifact_ids = {
            artifact_id
            for artifact_id, _, _ in citation_references(model_result.answer_text)
        }
        return sorted(cited_artifact_ids & result_artifact_ids)

    def supports_bounded_partial(self, *, context: ContextSnapshot) -> bool:
        return any(
            observation.status == "succeeded"
            and ToolSemanticCapability.QUERY_RESULT.value in observation.capabilities
            and bool(observation.artifact_ids)
            for observation in context.observations
        )
