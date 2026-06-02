from __future__ import annotations

from engine.agent.types import AgentRunResponse


def validate_agent_response_contract(response: AgentRunResponse) -> None:
    artifact_ids = {artifact.id for artifact in response.artifacts}
    evidence_ids = {
        evidence.artifact_id
        for evidence in (response.answer.evidence if response.answer else [])
    }
    missing_evidence = sorted(evidence_ids - artifact_ids)
    if missing_evidence:
        raise ValueError(f"Agent answer evidence references missing artifacts: {missing_evidence}")

    execution_success = bool((response.execution or {}).get("success"))
    if response.answer and response.answer.key_findings and not execution_success:
        raise ValueError("Agent answer cannot contain business findings without successful execution.")

    if response.error or not response.success:
        error_artifacts = [artifact for artifact in response.artifacts if artifact.type == "error"]
        if not error_artifacts:
            raise ValueError("Failed agent runs must include an error artifact.")
        if not any(str(artifact.payload.get("recovery_guidance") or "").strip() for artifact in error_artifacts):
            raise ValueError("Agent error artifacts must include recovery guidance.")
