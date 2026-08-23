"""P3 open Artifact type and schema_version contracts."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactPayloadContractRegistry,
    ArtifactType,
    register_artifact_payload_contract,
    validate_artifact_payload,
    validate_artifact_type,
)
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentArtifactRecord, AgentSession


def test_only_core_owned_flat_type_ids_remain_valid() -> None:
    assert validate_artifact_type(ArtifactType.MARKDOWN.value) == "markdown"
    with pytest.raises(ValueError, match="namespaced"):
        validate_artifact_type("result_view")


def test_new_extension_type_must_be_namespaced() -> None:
    assert validate_artifact_type("dbfox.workspace.code_patch") == (
        "dbfox.workspace.code_patch"
    )
    with pytest.raises(ValueError, match="namespaced"):
        validate_artifact_type("code_patch")


def test_known_type_with_unknown_future_version_is_soft_on_read() -> None:
    payload = {"content": "future", "futureField": True}
    assert validate_artifact_payload(
        "markdown",
        payload,
        schema_version=2,
        allow_unknown=True,
    ) == payload
    with pytest.raises(ValueError, match="schema_version=2"):
        validate_artifact_payload("markdown", payload, schema_version=2)


def test_artifact_payload_registry_registers_directly_and_freezes() -> None:
    class CodePatchPayload(BaseModel):
        path: str = Field(min_length=1)
        content_hash: str | None = None

    registry = ArtifactPayloadContractRegistry()
    registry.register("dbfox.workspace.code_patch", 1, CodePatchPayload)
    assert registry.get("dbfox.workspace.code_patch", 1) is CodePatchPayload
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dbfox.workspace.code_patch", 1, CodePatchPayload)

    registry.freeze()
    assert registry.frozen is True
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register("dbfox.workspace.code_patch", 2, CodePatchPayload)


def test_registered_extension_payload_can_be_written_without_core_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine.agent.artifact import artifact_payload_contracts

    monkeypatch.setattr(artifact_payload_contracts, "_frozen", False)

    class CodePatchPayload(BaseModel):
        path: str = Field(min_length=1)
        content_hash: str | None = None

    register_artifact_payload_contract(
        "dbfox.tests.code_patch_probe",
        1,
        CodePatchPayload,
    )
    payload = validate_artifact_payload(
        "dbfox.tests.code_patch_probe",
        {"path": "src/app.py"},
        schema_version=1,
    )
    assert payload["path"] == "src/app.py"


def test_known_payload_contract_uses_schema_version_1() -> None:
    payload = validate_artifact_payload(
        "markdown",
        {"content": "bounded"},
        schema_version=1,
    )
    assert payload["content"] == "bounded"

    with pytest.raises(ValueError, match="schema_version=2"):
        validate_artifact_payload("markdown", {"content": "bounded"}, schema_version=2)


def test_unknown_new_write_is_rejected_but_historical_read_is_soft() -> None:
    payload = {"path": "src/app.py"}
    with pytest.raises(ValueError, match="Unknown new Artifact type"):
        validate_artifact_payload(
            "dbfox.workspace.future_object",
            payload,
            schema_version=1,
        )
    assert validate_artifact_payload(
        "dbfox.workspace.future_object",
        payload,
        schema_version=1,
        allow_unknown=True,
    ) == payload


def test_artifact_draft_accepts_namespaced_type_and_schema_version() -> None:
    draft = ArtifactDraft(
        key="file",
        type="dbfox.workspace.future_object",
        schema_version=1,
        title="File snapshot",
        payload={"path": "src/app.py"},
    )
    assert draft.type == "dbfox.workspace.future_object"
    assert draft.schema_version == 1


def test_repository_persists_schema_version_and_reads_unknown_soft(
    db_session,
    test_resource,
) -> None:
    session_id = "session-open-artifact"
    db_session.add(
        AgentSession(
            id=session_id,
            title="Open artifact",
        )
    )
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version=1),),
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
        artifact_type=ArtifactType.MARKDOWN.value,
        title="Markdown",
        payload={"content": "bounded"},
    )
    db_session.commit()

    assert artifact.type == "markdown"
    assert artifact.schema_version == 1
    row = db_session.get(AgentArtifactRecord, artifact.id)
    assert row is not None and row.schema_version == 1

    unknown = ArtifactRepository._domain(
        AgentArtifactRecord(
            id="artifact_unknown_soft",
            run_id=admission.run_id,
            session_id=session_id,
            type="dbfox.workspace.future_object",
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
    assert unknown.type == "dbfox.workspace.future_object"
    assert unknown.payload == {"path": "src/app.py"}
