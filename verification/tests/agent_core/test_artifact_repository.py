"""Domain-neutral Artifact envelope and authority tests."""

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelation,
    ArtifactRelationType,
    ArtifactType,
    ArtifactVisibility,
)
from engine.agent.repositories.artifact import (
    ArtifactDraftContractError,
    ArtifactRepository,
    _set_payload_draft_ref,
)
from engine.agent.repositories.session import SessionRepository
from engine.agent.resource_refs import dump_resource_refs
from engine.models import AgentRun, AgentSession, AgentSessionInput
from engine.resource import ResourceScopeRef


RESOURCE = ResourceScopeRef(kind="verification.resource", id="resource-1", version=1)


def _active_run(db_session, session_id: str):
    db_session.add(AgentSession(id=session_id, title="Artifacts"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(RESOURCE,),
        content="Create a bounded work product.",
        idempotency_key=f"request-{session_id}",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={},
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    return admission, lease, turn


def _markdown(
    repository,
    *,
    lease,
    run_id,
    turn_id,
    title="Work product",
    relations=None,
    visibility=None,
):
    return repository.create(
        lease=lease,
        run_id=run_id,
        turn_id=turn_id,
        artifact_type=ArtifactType.MARKDOWN,
        title=title,
        payload={"content": title},
        resource_refs=(RESOURCE,),
        relations=relations or [],
        visibility=visibility,
    )


def test_get_for_run_never_exposes_cross_run_or_cross_session_artifacts(db_session):
    admission, lease, turn = _active_run(db_session, "artifact-read-scope")
    repository = ArtifactRepository(db_session)
    artifact = _markdown(
        repository,
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
    )
    assert repository.get_for_run(
        session_id=artifact.session_id, run_id=artifact.run_id, artifact_id=artifact.id
    ) == artifact
    assert repository.get_for_run(
        session_id=artifact.session_id, run_id="other", artifact_id=artifact.id
    ) is None
    assert repository.get_for_run(
        session_id="other", run_id=artifact.run_id, artifact_id=artifact.id
    ) is None


def test_relation_lookup_is_exactly_scoped_to_current_run(db_session):
    admission, lease, turn = _active_run(db_session, "artifact-relation-scope")
    repository = ArtifactRepository(db_session)
    source = _markdown(
        repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id), title="Source"
    )
    derived = _markdown(
        repository,
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        title="Derived",
        relations=[
            ArtifactRelation(
                relation=ArtifactRelationType.DERIVED_FROM,
                artifact_id=source.id,
            )
        ],
    )
    assert repository.artifacts_relating_to_for_run(
        session_id=source.session_id,
        run_id=source.run_id,
        artifact_id=source.id,
        relation=ArtifactRelationType.DERIVED_FROM,
    ) == (derived,)


def test_previous_artifact_is_fenced_by_session_resource_and_order(db_session):
    admission, lease, turn = _active_run(db_session, "artifact-availability")
    repository = ArtifactRepository(db_session)
    artifact = _markdown(
        repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id)
    )
    owner_run = db_session.get(AgentRun, admission.run_id)
    assert owner_run is not None
    owner_run.status = "completed"
    current_input = AgentSessionInput(
        id="artifact-consumer-input",
        session_id=artifact.session_id,
        run_id="artifact-consumer-run",
        sequence=2,
        idempotency_key="artifact-consumer",
        content="Continue",
        resource_refs_json=dump_resource_refs((RESOURCE,)),
    )
    current_run = AgentRun(
        id="artifact-consumer-run",
        session_id=artifact.session_id,
        input_id=current_input.id,
        session_sequence=2,
        question="Continue",
        status="running",
        request_json="{}",
    )
    db_session.add(current_input)
    db_session.flush()
    db_session.add(current_run)
    db_session.commit()
    assert repository.available_artifact(
        current_run_id=current_run.id,
        artifact_id=artifact.id,
        session_id=artifact.session_id,
    ) == artifact
    assert repository.available_artifact(
        current_run_id=current_run.id,
        artifact_id=artifact.id,
        session_id="other",
    ) is None


def test_internal_artifact_is_available_only_inside_its_own_run(db_session):
    admission, lease, turn = _active_run(db_session, "internal-artifact-availability")
    repository = ArtifactRepository(db_session)
    artifact = _markdown(
        repository,
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        visibility=ArtifactVisibility.INTERNAL,
    )
    assert repository.available_artifact(
        current_run_id=admission.run_id,
        artifact_id=artifact.id,
        session_id=artifact.session_id,
    ) == artifact

    owner_run = db_session.get(AgentRun, admission.run_id)
    assert owner_run is not None
    owner_run.status = "completed"
    current_input = AgentSessionInput(
        id="internal-artifact-consumer-input",
        session_id=artifact.session_id,
        run_id="internal-artifact-consumer-run",
        sequence=2,
        idempotency_key="internal-artifact-consumer",
        content="Continue",
        resource_refs_json=dump_resource_refs((RESOURCE,)),
    )
    current_run = AgentRun(
        id="internal-artifact-consumer-run",
        session_id=artifact.session_id,
        input_id=current_input.id,
        session_sequence=2,
        question="Continue",
        status="running",
        request_json="{}",
    )
    db_session.add(current_input)
    db_session.flush()
    db_session.add(current_run)
    db_session.commit()

    assert repository.available_artifact(
        current_run_id=current_run.id,
        artifact_id=artifact.id,
        session_id=artifact.session_id,
    ) is None


def test_artifact_draft_cannot_expand_run_resource_authority(db_session):
    admission, lease, turn = _active_run(db_session, "artifact-authority")
    unauthorized = ResourceScopeRef(kind="verification.resource", id="resource-2", version=1)
    repository = ArtifactRepository(db_session)
    try:
        repository.persist_drafts(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            invocation_id="invocation-1",
            tool_name="verification_tool",
            drafts=[
                ArtifactDraft(
                    key="outside",
                    type=ArtifactType.MARKDOWN,
                    title="Outside authority",
                    payload={"content": "bounded"},
                    resource_refs=(unauthorized,),
                )
            ],
        )
    except ArtifactDraftContractError as exc:
        assert "subset of the Run authority" in str(exc)
    else:
        raise AssertionError("Artifact draft expanded frozen Run authority")


def test_payload_draft_reference_supports_rfc6901_nested_paths():
    payload = {
        "source": {"artifactId": "pending"},
        "escaped/key": {"~identity": "pending"},
    }

    _set_payload_draft_ref(payload, "/source/artifactId", "artifact_source")
    _set_payload_draft_ref(
        payload,
        "/escaped~1key/~0identity",
        "artifact_escaped",
    )

    assert payload["source"]["artifactId"] == "artifact_source"
    assert payload["escaped/key"]["~identity"] == "artifact_escaped"


def test_payload_draft_reference_rejects_missing_nested_parent():
    try:
        _set_payload_draft_ref({}, "/source/artifactId", "artifact_source")
    except ArtifactDraftContractError as exc:
        assert "path does not exist" in str(exc)
    else:
        raise AssertionError("Missing JSON Pointer parent was accepted")
