"""Atomic settlement of one completed Tool attempt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from engine.agent.artifact import ArtifactPayloadContractResolver
from engine.agent.observation import ObservationStatus, serialize_model_observation
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.session import SessionLease
from engine.agent.tool import ToolInvocation
from engine.tools.runtime.base import BaseTool, ToolRecoveryPolicy
from engine.tools.runtime.observation import ToolObservationProjection
from engine.tools.runtime.result import ToolResult


_OUTPUT_CONTRACT_SUMMARY = "工具输出未通过合同校验。"


@dataclass(frozen=True)
class TransientToolOutput:
    """Provider input retained only in RunLoop memory for the current Run."""

    call_id: str
    output: str


class ToolSettlement:
    """Own the short transaction from ToolResult to Artifact and Observation."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        artifact_payload_contract_resolver: (
            ArtifactPayloadContractResolver | None
        ) = None,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_payload_contract_resolver = (
            artifact_payload_contract_resolver
        )

    def settle(
        self,
        lease: SessionLease,
        invocation: ToolInvocation,
        *,
        tool: BaseTool,
        result: ToolResult,
        needs_reconciliation: bool,
    ) -> TransientToolOutput:
        with self._session_factory() as db:
            artifacts = []
            output = result.output or {}
            if result.status == "success":
                artifacts = ArtifactRepository(
                    db,
                    payload_contract_resolver=(
                        self._artifact_payload_contract_resolver
                    ),
                ).persist_drafts(
                    lease=lease,
                    run_id=invocation.run_id,
                    turn_id=invocation.turn_id,
                    invocation_id=invocation.id,
                    tool_name=invocation.tool_name,
                    drafts=result.artifact_drafts,
                )
            artifact_ids = [item.id for item in artifacts]
            if (
                tool.spec.semantics.publishes_artifact_references
                and result.status == "success"
            ):
                for referenced_id in output.get("referenced_artifact_ids") or []:
                    value = str(referenced_id).strip()
                    if value and value not in artifact_ids:
                        artifact_ids.append(value)
            observation = (
                ToolObservationProjection(summary=_OUTPUT_CONTRACT_SUMMARY)
                if result.error_code == "TOOL_OUTPUT_CONTRACT_FAILED"
                else tool.project_observation(
                    status=result.status,
                    output=output,
                    artifacts=artifacts,
                )
            )
            status = self._observation_status(
                result,
                needs_reconciliation=needs_reconciliation,
            )
            succeeded = status is ObservationStatus.SUCCEEDED
            retryable = (
                result.status != "success"
                and tool.execution.recovery is ToolRecoveryPolicy.RETRY_SAFE
                and tool.execution.retryable
                and result.error_code
                not in {
                    "TOOL_CANCELLED",
                    "TOOL_TIMEOUT",
                    "TOOL_OUTPUT_CONTRACT_FAILED",
                }
            )
            error_code = (
                None
                if result.status == "success"
                else (result.error_code or "TOOL_EXECUTION_FAILED")
            )
            ToolInvocationRepository(db).settle(
                lease=lease,
                invocation_id=invocation.id,
                status=status,
                model_visible_summary=observation.summary,
                artifact_ids=artifact_ids,
                facts=observation.facts,
                capabilities=(
                    tuple(str(capability) for capability in tool.spec.semantics.produces)
                    if succeeded
                    else ()
                ),
                contributes_progress=(
                    succeeded and tool.spec.semantics.contributes_progress
                ),
                error_code=error_code,
                error_message=result.error,
                retryable=retryable,
            )
            db.commit()
            provider_facts = (
                observation.provider_payload
                if succeeded and observation.provider_payload
                else observation.facts
            )
            return TransientToolOutput(
                call_id=str(invocation.provider_call_id),
                output=serialize_model_observation(
                    status=status.value,
                    summary=observation.summary,
                    facts=provider_facts,
                    artifact_ids=artifact_ids,
                    retryable=retryable,
                    error_code=error_code,
                    error_message=result.error,
                ),
            )

    @staticmethod
    def _observation_status(
        result: ToolResult,
        *,
        needs_reconciliation: bool,
    ) -> ObservationStatus:
        if result.status == "success":
            return ObservationStatus.SUCCEEDED
        if result.error_code == "TOOL_CANCELLED":
            return ObservationStatus.CANCELLED
        outcome_unknown = result.error_code in {
            "TOOL_OUTCOME_UNKNOWN",
            "TOOL_TIMEOUT",
        }
        if outcome_unknown and needs_reconciliation:
            return ObservationStatus.UNKNOWN
        return ObservationStatus.FAILED
