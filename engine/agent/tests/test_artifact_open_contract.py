"""P3 open Artifact type and schema_version contracts."""

from __future__ import annotations

import pytest

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactType,
    validate_artifact_payload,
    validate_artifact_type,
)
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentArtifactRecord, AgentSession


def test_legacy_flat_type_ids_remain_valid() -> None:
    assert validate_artifact_type("result_view") == "result_view"
    assert validate_artifact_type(ArtifactType.SQL.value) == "sql"


def test_new_extension_type_must_be_namespaced() -> None:
    assert validate_artifact_type("dbfox.workspace.code_patch") == (
        "dbfox.workspace.code_patch"
    )
    with pytest.raises(ValueError, match="namespaced"):
        validate_artifact_type("code_patch")


def test_known_payload_contract_uses_schema_version_1() -> None:
    payload = validate_artifact_payload(
        "sql",
        {
            "sql": "SELECT 1",
            "safeSql": "SELECT 1",
            "dialect": "sqlite",
            "queryFingerprint": "fingerprint",
        },
        schema_version=1,
    )
    assert payload["safeSql"] == "SELECT 1"

    with pytest.raises(ValueError, match="schema_version=2"):
        validate_artifact_payload("sql", {"sql": "SELECT 1"}, schema_version=2)


def test_unknown_new_write_is_rejected_but_historical_read_is_soft() -> None:
    payload = {"path": "src/app.py"}
    with pytest.raises(ValueError, match="Unknown new Artifact type"):
        validate_artifact_payload(
            "dbfox.workspace.file_snapshot",
            payload,
            schema_version=1,
        )
    assert validate_artifact_payload(
        "dbfox.workspace.file_snapshot",
        payload,
        schema_version=1,
        allow_unknown=True,
    ) == payload


def test_artifact_draft_accepts_namespaced_type_and_schema_version() -> None:
    draft = ArtifactDraft(
        key="file",
        type="dbfox.workspace.file_snapshot",
        schema_version=1,
        title="File snapshot",
        payload={"path": "src/app.py"},
    )
    assert draft.type == "dbfox.workspace.file_snapshot"
    assert draft.schema_version == 1


def test_repository_persists_schema_version_and_reads_unknown_soft(
    db_session,
    test_datasource,
) -> None:
    session_id = "session-open-artifact"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Open artifact",
        )
    )
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="test",
        idempotency_key="open-artifact",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = SessionRepository(db_session).claim(
        session_id=session_id,
        owner="test",
    )
    assert lease is not None
    artifact = ArtifactRepository(db_session).create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=None,
        artifact_type=ArtifactType.SQL.value,
        title="SQL",
        payload={
            "sql": "SELECT 1",
            "safeSql": "SELECT 1",
            "dialect": "sqlite",
            "queryFingerprint": "fingerprint",
        },
    )
    db_session.commit()

    assert artifact.type == "sql"
    assert artifact.schema_version == 1
    row = db_session.get(AgentArtifactRecord, artifact.id)
    assert row is not None and row.schema_version == 1

    unknown = ArtifactRepository._domain(
        AgentArtifactRecord(
            id="artifact_unknown_soft",
            run_id=admission.run_id,
            session_id=session_id,
            type="dbfox.workspace.file_snapshot",
            schema_version=1,
            title="Unknown",
            payload_json='{"path":"src/app.py"}',
            presentation_json="{}",
            refs_json="{}",
            provenance_json="{}",
            relations_json="[]",
            status="completed",
        )
    )
    assert unknown.type == "dbfox.workspace.file_snapshot"
    assert unknown.payload == {"path": "src/app.py"}
