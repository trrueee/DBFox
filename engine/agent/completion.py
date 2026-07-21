"""Deterministic completion policy for the dynamic Agent loop."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from engine.agent.context import ContextSnapshot
from engine.agent.evidence import citation_references
from engine.agent.turn import ModelTurnResult


class CompletionKind(StrEnum):
    CONTINUE = "continue"
    REPAIR = "repair"
    ASK_USER = "ask_user"
    SYNTHESIZE = "synthesize"
    PARTIAL = "partial"
    FAIL = "fail"


class TaskKind(StrEnum):
    DIRECT = "direct"
    SCHEMA = "schema"
    LOOKUP = "lookup"
    ANALYTICAL = "analytical"


class CompletionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CompletionKind
    reason: str
    missing: list[str] = Field(default_factory=list)


class CompletionPolicy:
    """Provider output is advisory; durable observations decide completion."""

    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        model_result: ModelTurnResult,
        task_kind: TaskKind,
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
        database_task = task_kind in {TaskKind.LOOKUP, TaskKind.ANALYTICAL}
        result_observations = [
            item for item in successes if item.tool_name == "sql.execute_readonly"
        ]
        result_artifact_ids = {
            artifact_id
            for observation in result_observations
            for artifact_id in observation.artifact_ids
        }
        cited_artifact_ids = {
            artifact_id for artifact_id, _, _ in citation_references(model_result.text)
        }
        ready_reviews = [
            item for item in successes
            if item.tool_name == "analysis.review" and item.facts.get("ready") is True
        ]

        if turn_count >= max_turns:
            if result_observations or successes or task_kind is TaskKind.DIRECT:
                return CompletionDecision(
                    kind=CompletionKind.PARTIAL,
                    reason="The run reached its turn budget with usable verified work.",
                )
            return CompletionDecision(
                kind=CompletionKind.FAIL,
                reason="The run reached its turn budget without verified database evidence.",
                missing=["verified_result"],
            )

        if failures and not model_result.text.strip():
            return CompletionDecision(
                kind=CompletionKind.REPAIR,
                reason="The latest failed tool call needs a model-visible repair turn.",
            )

        if database_task and not result_observations:
            return CompletionDecision(
                kind=CompletionKind.CONTINUE,
                reason="A database answer requires a successful readonly result observation.",
                missing=["verified_result", "evidence"],
            )

        if task_kind is TaskKind.SCHEMA and not successes:
            return CompletionDecision(
                kind=CompletionKind.CONTINUE,
                reason="A schema answer requires a successful metadata observation.",
                missing=["verified_schema_observation"],
            )

        if task_kind is TaskKind.ANALYTICAL and not ready_reviews:
            return CompletionDecision(
                kind=CompletionKind.CONTINUE,
                reason="The analytical goal needs an evidence-linked coverage review before synthesis.",
                missing=["analysis_coverage_review"],
            )

        if database_task and not (cited_artifact_ids & result_artifact_ids):
            return CompletionDecision(
                kind=CompletionKind.CONTINUE,
                reason="Database claims must cite an observed result Artifact inline.",
                missing=["inline_evidence"],
            )

        if not model_result.text.strip():
            return CompletionDecision(
                kind=CompletionKind.CONTINUE,
                reason="The model has not produced an answer candidate.",
                missing=["answer"],
            )

        return CompletionDecision(
            kind=CompletionKind.SYNTHESIZE,
            reason="The answer candidate is supported by the available durable observations.",
        )
