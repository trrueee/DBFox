"""Domain-neutral Artifact envelope and authority tests."""

from uuid import uuid4

import pytest

from engine.agent.artifact import (
    ArtifactDraft,
    ArtifactRelation,
    ArtifactRelationDraft,
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
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.observation import ObservationStatus
from engine.agent.resource_refs import dump_resource_refs
from engine.agent.run import SessionLeaseConflict
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, AgentSessionInput, AgentToolInvocation, AgentTurn
from engine.resource import ResourceScopeRef
from engine.tools.materialization import materialize_tools
from verification.support.agent_tools import verification_registry


RESOURCE = ResourceScopeRef(kind="verification.resource", id="resource-1", version=1)


def _tools():
    return materialize_tools(
        verification_registry(), allowed_groups={"verification"}, execution_mode="user_requested_read",
    )


def _request(repository, *, lease, run_id, turn_id, refs=(RESOURCE,)):
    return ToolInvocationRepository(repository.session).request(
        lease=lease, run_id=run_id, turn_id=turn_id,
        provider_call_id=f"call_{uuid4().hex}", tool_name="verification_read",
        raw_input={}, materialization=_tools(),
        policy_decision={"status": "allowed", "safe_args": {}}, resource_refs=refs,
    )


def _draft(*, refs=(RESOURCE,), key="work", relations=()):
    return ArtifactDraft(
        key=key, type=ArtifactType.MARKDOWN, title="Work",
        payload={"content": "bounded"}, resource_refs=refs, relations=relations,
    )


def _settle(repository, *, lease, invocation, drafts):
    artifacts = repository.persist_drafts(
        lease=lease, run_id=invocation.run_id, turn_id=invocation.turn_id,
        invocation_id=invocation.id, tool_name=invocation.tool_name, drafts=drafts,
    )
    ToolInvocationRepository(repository.session).settle(
        lease=lease, invocation_id=invocation.id, status=ObservationStatus.SUCCEEDED,
        model_visible_summary="Created", artifact_ids=[item.id for item in artifacts],
    )
    return artifacts


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
        tool_materialization=_tools().model_dump(mode="json"),
        tool_materialization_hash=_tools().hash,
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
    invocation = _request(repository, lease=lease, run_id=run_id, turn_id=turn_id)
    return _settle(repository, lease=lease, invocation=invocation, drafts=[ArtifactDraft(
        key="work", type=ArtifactType.MARKDOWN, title=title, payload={"content": title},
        resource_refs=(RESOURCE,), visibility=visibility,
        relations=tuple(ArtifactRelationDraft(
            relation=item.relation, artifact_id=item.artifact_id,
        ) for item in relations or []),
    )])[0]


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
    current_input.resource_refs_json = dump_resource_refs((RESOURCE.model_copy(update={"version": 2}),))
    assert repository.available_artifact(
        current_run_id=current_run.id, artifact_id=artifact.id, session_id=artifact.session_id,
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


def test_artifact_draft_cannot_expand_invocation_resource_authority(db_session):
    admission, lease, turn = _active_run(db_session, "artifact-authority")
    unauthorized = ResourceScopeRef(kind="verification.resource", id="resource-2", version=1)
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    try:
        repository.persist_drafts(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            invocation_id=invocation.id,
            tool_name=invocation.tool_name,
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
        assert "exceed its Invocation" in str(exc)
    else:
        raise AssertionError("Artifact draft expanded frozen Invocation authority")


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


def test_new_invocation_resource_is_readable_in_same_run_without_changing_input(db_session):
    admission, lease, turn = _active_run(db_session, "new-resource")
    repository = ArtifactRepository(db_session)
    created_ref = ResourceScopeRef(kind=RESOURCE.kind, id="new-document", version="3")
    invocation = _request(repository, lease=lease, run_id=admission.run_id,
                          turn_id=str(turn.id), refs=(created_ref,))
    artifact = _settle(repository, lease=lease, invocation=invocation,
                       drafts=[_draft(refs=(created_ref,))])[0]
    assert repository.available_artifact(session_id=lease.session_id,
                                        current_run_id=admission.run_id, artifact_id=artifact.id) == artifact
    run = db_session.get(AgentRun, admission.run_id)
    assert db_session.get(AgentSessionInput, run.input_id).resource_refs_json == dump_resource_refs((RESOURCE,))
    assert artifact.provenance == {"tool_invocation_id": invocation.id, "tool_name": invocation.tool_name}


def test_empty_scope_composition_inherits_only_explicit_artifact_refs(db_session):
    admission, lease, turn = _active_run(db_session, "derived-authority")
    repository = ArtifactRepository(db_session)
    extra = ResourceScopeRef(kind=RESOURCE.kind, id="not-in-artifact", version=1)
    producer = _request(repository, lease=lease, run_id=admission.run_id,
                        turn_id=str(turn.id), refs=(RESOURCE, extra))
    source = _settle(repository, lease=lease, invocation=producer, drafts=[_draft()])[0]
    child = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id), refs=())
    relation = ArtifactRelationDraft(relation=ArtifactRelationType.DERIVED_FROM, artifact_id=source.id)
    derived = _settle(repository, lease=lease, invocation=child,
                      drafts=[_draft(relations=(relation,))])[0]
    assert derived.resource_refs == (RESOURCE,)
    assert db_session.get(AgentToolInvocation, child.id).resource_refs_json == "[]"
    assert repository.available_artifact(session_id=lease.session_id,
                                        current_run_id=admission.run_id, artifact_id=derived.id) == derived
    illegal = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id), refs=())
    with pytest.raises(ArtifactDraftContractError, match="exceed"):
        _settle(repository, lease=lease, invocation=illegal,
                drafts=[_draft(refs=(extra,), relations=(relation,))])


@pytest.mark.parametrize("fault", ["missing", "session", "run", "turn", "tool", "turn_run", "turn_session"])
def test_batch_requires_exact_persisted_invocation_ownership(db_session, fault):
    admission, lease, turn = _active_run(db_session, f"identity-{fault}")
    foreign, _foreign_lease, foreign_turn = _active_run(db_session, f"foreign-{fault}")
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    row = db_session.get(AgentToolInvocation, invocation.id)
    arguments = dict(lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
                     invocation_id=invocation.id, tool_name=invocation.tool_name, drafts=[_draft()])
    if fault == "missing":
        arguments["invocation_id"] = "missing-invocation"
    elif fault == "session":
        row.session_id = f"foreign-{fault}"
    elif fault == "run":
        row.run_id = foreign.run_id
    elif fault == "turn":
        row.turn_id = str(foreign_turn.id)
    elif fault == "tool":
        arguments["tool_name"] = "foreign_wire_tool"
    elif fault == "turn_run":
        db_session.get(AgentTurn, turn.id).run_id = foreign.run_id
        db_session.get(AgentTurn, turn.id).sequence = 2
    else:
        db_session.get(AgentTurn, turn.id).session_id = f"foreign-{fault}"
    with pytest.raises(ArtifactDraftContractError, match="identity"):
        repository.persist_drafts(**arguments)
    assert db_session.query(AgentArtifactRecord).count() == 0


@pytest.mark.parametrize("encoded", ["null", "{", "{}", '[{"kind":"verification.resource","id":"x"},{"kind":"verification.resource","id":"x"}]'])
def test_invalid_persisted_invocation_refs_fail_closed(db_session, encoded):
    admission, lease, turn = _active_run(db_session, "invalid-refs")
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    db_session.get(AgentToolInvocation, invocation.id).resource_refs_json = encoded
    with pytest.raises(ArtifactDraftContractError):
        _settle(repository, lease=lease, invocation=invocation, drafts=[_draft()])
    assert db_session.query(AgentArtifactRecord).count() == 0


@pytest.mark.parametrize("fault", ["no_relation", "wrong_relation", "wrong_version", "missing_provenance", "foreign_provenance", "failed", "cross_run"])
def test_forged_or_stale_derivation_cannot_inherit_authority(db_session, fault):
    admission, lease, turn = _active_run(db_session, "bad-derivation")
    repository = ArtifactRepository(db_session)
    source = _markdown(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    source_row = db_session.get(AgentArtifactRecord, source.id)
    if fault == "missing_provenance":
        source_row.provenance_json = "{}"
    elif fault == "foreign_provenance":
        source_row.provenance_json = '{"tool_invocation_id":"foreign","tool_name":"verification_read"}'
    elif fault == "failed":
        source_row.status = "failed"
    elif fault == "cross_run":
        # A historical relation remains legal lineage but contributes no scope.
        other_run = AgentRun(id="old-source-run", session_id=lease.session_id,
                             input_id=admission.input_id, session_sequence=0, question="Old",
                             status="completed", request_json="{}")
        db_session.add(other_run)
        source_row.run_id = other_run.id
    refs = (RESOURCE.model_copy(update={"version": "1"}),) if fault == "wrong_version" else (RESOURCE,)
    relations = () if fault == "no_relation" else (ArtifactRelationDraft(
        relation=ArtifactRelationType.SUPPORTS if fault == "wrong_relation" else ArtifactRelationType.DERIVED_FROM,
        artifact_id=source.id,
    ),)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id), refs=())
    with pytest.raises(ArtifactDraftContractError):
        _settle(repository, lease=lease, invocation=invocation,
                drafts=[_draft(refs=refs, relations=relations)])
    assert db_session.query(AgentArtifactRecord).count() == 1


@pytest.mark.parametrize("fault", ["authority", "payload", "pointer"])
def test_batch_failure_does_not_insert_or_select_earlier_valid_artifact(db_session, fault):
    admission, lease, turn = _active_run(db_session, "atomic-authority")
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    invalid = RESOURCE.model_copy(update={"version": 2})
    drafts = [_draft(key="first").model_copy(update={"select_if_none": True}),
              _draft(key="second", refs=(invalid,))]
    if fault == "payload":
        drafts[1] = _draft(key="second").model_copy(update={"payload": {"content": []}})
    elif fault == "pointer":
        drafts[1] = _draft(key="second").model_copy(update={"payload_draft_refs": {"/missing/id": "first"}})
    with pytest.raises(ArtifactDraftContractError):
        _settle(repository, lease=lease, invocation=invocation, drafts=drafts)
    assert db_session.query(AgentArtifactRecord).count() == 0
    assert db_session.get(AgentSession, lease.session_id).selected_artifact_id is None
    assert db_session.get(AgentToolInvocation, invocation.id).status == "requested"


def test_batch_derived_graph_is_atomic_and_rejects_cycles(db_session):
    admission, lease, turn = _active_run(db_session, "draft-graph")
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    left = _draft(key="left", relations=(ArtifactRelationDraft(
        relation=ArtifactRelationType.DERIVED_FROM, draft_key="right"),))
    right = _draft(key="right", relations=(ArtifactRelationDraft(
        relation=ArtifactRelationType.DERIVED_FROM, draft_key="left"),))
    with pytest.raises(ArtifactDraftContractError, match="cycle"):
        _settle(repository, lease=lease, invocation=invocation, drafts=[left, right])
    assert db_session.query(AgentArtifactRecord).count() == 0
    artifacts = _settle(repository, lease=lease, invocation=invocation,
                        drafts=[left, _draft(key="right")])
    assert artifacts[0].relations[0].artifact_id == artifacts[1].id
    assert repository.available_artifact(session_id=lease.session_id,
                                        current_run_id=admission.run_id, artifact_id=artifacts[0].id) == artifacts[0]


@pytest.mark.parametrize("budget,limit", [("MAX_SOURCE_PROOF_NODES", 1), ("MAX_SOURCE_PROOF_EDGES", 0), ("MAX_SOURCE_PROOF_DEPTH", 0)])
def test_source_proof_budgets_fail_closed(db_session, monkeypatch, budget, limit):
    import engine.agent.repositories.artifact as artifact_module

    admission, lease, turn = _active_run(db_session, "proof-budget")
    repository = ArtifactRepository(db_session)
    source = _markdown(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id), refs=())
    relation = ArtifactRelationDraft(relation=ArtifactRelationType.DERIVED_FROM, artifact_id=source.id)
    monkeypatch.setattr(artifact_module, budget, limit)
    with pytest.raises(ArtifactDraftContractError, match="budget"):
        _settle(repository, lease=lease, invocation=invocation, drafts=[_draft(relations=(relation,))])
    monkeypatch.setattr(artifact_module, budget, limit + 1)
    assert len(_settle(repository, lease=lease, invocation=invocation,
                       drafts=[_draft(relations=(relation,))])) == 1


def test_recovery_settles_original_invocation_only_once(db_session):
    admission, lease, turn = _active_run(db_session, "reconcile-proof")
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    invocations = ToolInvocationRepository(db_session)
    invocations.mark_running(lease=lease, invocation_id=invocation.id)
    db_session.get(AgentToolInvocation, invocation.id).recovery_policy = "reconcile"
    # Recovery keeps the original Invocation identity and its frozen refs.
    db_session.commit()
    recovered = invocations.recover_interrupted(lease=lease, run_id=admission.run_id)
    assert [item.id for item in recovered] == [invocation.id]
    artifacts = _settle(repository, lease=lease, invocation=recovered[0], drafts=[_draft()])
    assert artifacts[0].provenance["tool_invocation_id"] == invocation.id
    with pytest.raises(ArtifactDraftContractError, match="again"):
        _settle(repository, lease=lease, invocation=recovered[0], drafts=[_draft()])
    assert db_session.query(AgentArtifactRecord).count() == 1


def test_historical_envelope_does_not_gain_agent_authority(db_session):
    admission, lease, turn = _active_run(db_session, "legacy-proof")
    repository = ArtifactRepository(db_session)
    artifact = repository.create(lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
                                 artifact_type=ArtifactType.MARKDOWN, title="Historical",
                                 payload={"content": "old"}, resource_refs=(RESOURCE,))
    assert repository.get(artifact.id) == artifact
    assert repository.available_artifact(session_id=lease.session_id,
                                        current_run_id=admission.run_id, artifact_id=artifact.id) is None


@pytest.mark.parametrize("fault", ["session-token", "run-token"])
def test_artifact_writes_require_the_current_session_and_run_lease(db_session, fault):
    admission, lease, turn = _active_run(db_session, "artifact-lease")
    repository = ArtifactRepository(db_session)
    invocation = _request(repository, lease=lease, run_id=admission.run_id, turn_id=str(turn.id))
    if fault == "session-token":
        db_session.get(AgentSession, lease.session_id).lease_token += 1
    else:
        db_session.get(AgentRun, admission.run_id).lease_token += 1
    with pytest.raises(SessionLeaseConflict):
        _settle(repository, lease=lease, invocation=invocation, drafts=[_draft()])
    assert db_session.query(AgentArtifactRecord).count() == 0
