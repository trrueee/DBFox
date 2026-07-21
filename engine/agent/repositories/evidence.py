"""Persistence boundary for answer evidence and exact Artifact links."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from engine.agent.evidence import Evidence
from engine.agent.repositories.write_transaction import begin_agent_write
from engine.models import AgentArtifactRecord, AgentEvidenceRecord


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class EvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_all(self, *, session_id: str, run_id: str, evidence: list[Evidence]) -> None:
        begin_agent_write(self.session)
        for item in evidence:
            if item.session_id != session_id or item.run_id != run_id:
                raise ValueError("Evidence is outside the terminal Run")
            artifact = self.session.get(AgentArtifactRecord, item.artifact_id)
            if artifact is None or str(artifact.session_id) != session_id:
                raise ValueError(f"Evidence references an unavailable Artifact: {item.artifact_id}")
            existing = self.session.get(AgentEvidenceRecord, item.id)
            if existing is not None:
                if str(existing.artifact_id) != item.artifact_id or str(existing.claim_id) != item.claim_id:
                    raise ValueError(f"Evidence identity conflict: {item.id}")
                continue
            self.session.add(
                AgentEvidenceRecord(
                    id=item.id,
                    session_id=session_id,
                    run_id=run_id,
                    claim_id=item.claim_id,
                    artifact_id=item.artifact_id,
                    label=item.label,
                    query_fingerprint=item.query_fingerprint,
                    observed_at=item.observed_at,
                    locator_json=_json(item.locator.model_dump(mode="json")),
                    value_json=_json(item.value) if item.value is not None else None,
                )
            )
