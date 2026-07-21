"""Deterministic terminal response composition and Evidence validation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.agent.artifact import Artifact, ArtifactSelectionSuggestion
from engine.agent.evidence import Evidence


class CompletionDisposition(StrEnum):
    COMPLETE = "complete"
    BOUNDED_PARTIAL = "bounded_partial"


class CompletionLimitationCode(StrEnum):
    TURN_BUDGET_REACHED = "TURN_BUDGET_REACHED"
    TOOL_BUDGET_REACHED = "TOOL_BUDGET_REACHED"
    TOKEN_BUDGET_REACHED = "TOKEN_BUDGET_REACHED"
    COST_BUDGET_REACHED = "COST_BUDGET_REACHED"
    DEADLINE_REACHED = "DEADLINE_REACHED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TOOL_REJECTED = "TOOL_REJECTED"
    PROVIDER_LIMIT = "PROVIDER_LIMIT"
    NO_PROGRESS = "NO_PROGRESS"


class AnswerCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    key_findings: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class ComposedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    run_id: str
    completion_disposition: CompletionDisposition
    limitation_codes: list[CompletionLimitationCode] = Field(default_factory=list)
    answer: AnswerCandidate
    artifacts: list[Artifact]
    referenced_artifact_ids: list[str]
    selection_suggestion: ArtifactSelectionSuggestion | None = None

    @model_validator(mode="after")
    def validate_completion_contract(self) -> "ComposedResponse":
        if self.completion_disposition is CompletionDisposition.COMPLETE and self.limitation_codes:
            raise ValueError("Complete responses cannot declare limitation codes")
        if self.completion_disposition is CompletionDisposition.BOUNDED_PARTIAL and not self.limitation_codes:
            raise ValueError("Bounded partial responses require at least one limitation code")
        return self


class ResponseCompositionError(ValueError):
    pass


class ResponseComposer:
    """Compose terminal product state; never infer or rewrite Artifact identity."""

    def compose(
        self,
        *,
        session_id: str,
        run_id: str,
        completion_disposition: CompletionDisposition,
        limitation_codes: list[CompletionLimitationCode] | None,
        answer: AnswerCandidate,
        artifacts: list[Artifact],
        selection_suggestion: ArtifactSelectionSuggestion | None = None,
    ) -> ComposedResponse:
        artifact_by_id = {artifact.id: artifact for artifact in artifacts}
        if len(artifact_by_id) != len(artifacts):
            raise ResponseCompositionError("Artifact IDs must be unique")
        for artifact in artifacts:
            if artifact.session_id != session_id or artifact.run_id != run_id:
                raise ResponseCompositionError("Artifact is outside the response aggregate")

        referenced: list[str] = []
        for evidence in answer.evidence:
            if evidence.session_id != session_id or evidence.run_id != run_id:
                raise ResponseCompositionError("Evidence is outside the response aggregate")
            if evidence.artifact_id not in artifact_by_id:
                raise ResponseCompositionError(
                    f"Evidence references an unknown Artifact ID: {evidence.artifact_id}"
                )
            if evidence.artifact_id not in referenced:
                referenced.append(evidence.artifact_id)

        if selection_suggestion and selection_suggestion.artifact_id not in artifact_by_id:
            raise ResponseCompositionError("Selection suggestion references an unknown Artifact ID")

        return ComposedResponse(
            session_id=session_id,
            run_id=run_id,
            completion_disposition=completion_disposition,
            limitation_codes=limitation_codes or [],
            answer=answer,
            artifacts=artifacts,
            referenced_artifact_ids=referenced,
            selection_suggestion=selection_suggestion,
        )
