"""Attack real Scene producers and Workbench reference admission boundaries."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, ContextContributionInput, ContextFragment, ToolKey
from engine.agent.completion import CompletionGate
from engine.agent.context import ContextAssembler
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.plan import PlanStep, PlanStepStatus
from engine.agent.references import ConversationInputReference
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.plan import PlanRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.resource_refs import resource_refs_for_run
from engine.api.conversation_commands import _reference_resource_identities
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, AgentToolInvocation
from engine.runtime_composition import (authorize_project_resources, build_attempt_resource_resolver,
    build_default_completion_policy, default_capability_guidance, default_context_contributors)
from verification.bench.capabilities.dbfox_scene.runtime import SceneRuntime, SceneScript, _run_segment
from verification.bench.capabilities.dbfox_scene.schema import SceneCase, Step


@pytest.fixture
def produced(tmp_path):
    with SceneRuntime(tmp_path / "artifact-red") as runtime:
        case = SceneCase(case_id="red-producer", category="adversarial", prompt="Create a stable mesh and export the current revision.", steps=(
            Step(id="create", tool="scene_create", arguments={"title":"Red producer"}),
            Step(id="mesh", tool="object_create", arguments={"scene_id":"$scene_id","expected_version":"$version", "operation":{
                "kind":"object_create","objects":[{"id":"red-mesh","kind":"mesh","name":"Red Mesh"}]}}),
            Step(id="export", tool="scene_export", arguments={"scene_id":"$scene_id","expected_version":"$version"}),
        ))
        evidence, script = _run_segment(runtime, case, repetition=1)
        assert evidence["run_status"] == "completed" and len(evidence["artifacts"]) == 3
        assert all(item["status"] == "succeeded" for item in evidence["invocations"])
        yield runtime, evidence, script.scene


def reference(scene, artifact_id=None):
    # Exact public Scene referenceFor shape after conversationStore's wire projection.
    return ConversationInputReference.model_validate({"label":scene["title"],
        "authority":{"kind":"dbfox.scene.document","id":scene["id"]},
        "object":{"kind":"dbfox.scene.document","id":scene["id"],"version":scene["version"]},
        "locator":"/", "artifact_id":artifact_id})


def admit(runtime, evidence, attached, *, other_session=False):
    session_id = evidence["session_id"]
    references=attached if isinstance(attached,tuple) else (attached,)
    with runtime.factory() as db:
        if other_session:
            session_id = "red-other-" + uuid4().hex
            db.add(AgentSession(id=session_id, project_id=evidence["project_id"], title="Another chat"))
            db.commit()
        refs = authorize_project_resources(db, evidence["project_id"],
            _reference_resource_identities(references), snapshot=runtime.snapshot)
        sessions = SessionRepository(db)
        admission = sessions.admit(session_id=session_id, resource_refs=refs, references=references,
            content="Inspect the referenced current Scene; make one explicitly targeted edit.",
            idempotency_key=uuid4().hex, llm_credential_id="red-scripted", api_base=None,
            model_name="scripted", request_payload={"purpose":"Scene adversarial reference"})
        lease = sessions.claim(session_id=session_id, owner="scene-bench", ttl_seconds=600)
        assert lease is not None
        sessions.promote_next_input(lease=lease)
        db.commit()
    return admission, lease


def execute_reference(runtime, admission, lease, scene):
    case = SceneCase(case_id="red-consumer", category="adversarial", prompt="Inspect then transform the stable selected mesh.", steps=(
        Step(id="inspect", tool="scene_inspect", arguments={"scene_id":scene["id"]}),
        Step(id="transform", tool="object_transform", arguments={"scene_id":"$scene_id","expected_version":"$version",
            "operation":{"kind":"object_transform","transforms":[{"object_id":"red-mesh","position":[2,0,0]}]}}),
    ))
    script = SceneScript(case, lambda _:None, {item.tool.name: runtime.registry.provider_name_for_key(
        ToolKey(owner_id="dbfox.scene", local_name=item.tool.name)) for item in runtime.snapshot.tools if item.owner_id=="dbfox.scene"})
    snap=runtime.snapshot
    loop = RunLoop(session_factory=runtime.factory, model_factory=lambda _:script, registry=runtime.registry,
        context_contributors=default_context_contributors(snap), capability_guidance=default_capability_guidance(snap),
        resource_providers=snap.resource_providers, resource_resolver=build_attempt_resource_resolver(snapshot=snap),
        artifact_payload_contract_resolver=lambda kind,version:snap.get_artifact_contract(kind,version).validator,
        runtime_snapshot_id=snap.snapshot_id, completion=CompletionGate(build_default_completion_policy(snap)), live_stream=LiveStreamHub())
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
    assert script.observations["inspect"]["facts"]["scene"]["version"] == 2
    assert script.observations["transform"]["facts"]["scene"]["version"] == 3
    with runtime.factory() as db:
        assert db.get(AgentRun,admission.run_id).status == "completed"


def test_producer_refs_are_input_version_and_export_is_current_version(produced):
    runtime, evidence, scene = produced
    created, mutated, exported = evidence["artifacts"]
    assert created["payload"]["version"] == 1 and created["resource_refs"][0]["kind"] == "dbfox.scene.library"
    assert mutated["payload"]["version"] == 2 and mutated["resource_refs"][0]["version"] == 1
    assert exported["payload"]["version"] == 2 and exported["resource_refs"][0]["version"] == 2
    with runtime.factory() as db:
        repo=ArtifactRepository(db)
        assert all(repo.available_artifact(session_id=evidence["session_id"],current_run_id=evidence["run_id"],artifact_id=a["id"]) for a in evidence["artifacts"])
    admission, _ = admit(runtime,evidence,reference(scene,exported["id"]))
    with runtime.factory() as db:
        repo=ArtifactRepository(db)
        available=[repo.available_artifact(session_id=evidence["session_id"],current_run_id=admission.run_id,artifact_id=a["id"]) is not None for a in evidence["artifacts"]]
        assert available == [False,False,True]


@pytest.mark.parametrize("attachment", ["document", "export_same_session", "export_other_session", "mutation_artifact"])
def test_onask_reference_inspect_then_edit_uses_current_authority(produced, attachment):
    runtime,evidence,scene=produced
    artifact_id = None if attachment=="document" else evidence["artifacts"][1 if attachment=="mutation_artifact" else 2]["id"]
    admission,lease=admit(runtime,evidence,reference(scene,artifact_id),other_session=attachment=="export_other_session")
    with runtime.factory() as db:
        context=ContextAssembler(db).build(admission.run_id)
        assert context.input_references[0].object.version == 2
        assert resource_refs_for_run(db,db.get(AgentRun,admission.run_id))[0].version == 2
        available=ArtifactRepository(db).available_artifact(session_id=lease.session_id,current_run_id=admission.run_id,artifact_id=artifact_id) if artifact_id else None
        assert (available is not None) == (attachment=="export_same_session")
    execute_reference(runtime,admission,lease,scene)


@pytest.mark.parametrize("damage", ["internal", "producer_failed", "wrong_producer", "future", "nonterminal", "stale_fence"])
def test_selected_artifact_context_cannot_bypass_availability_proof(produced, damage):
    runtime,evidence,scene=produced
    selected=evidence["artifacts"][1 if damage=="stale_fence" else 2]["id"]
    admission,_=admit(runtime,evidence,reference(scene,selected))
    with runtime.factory() as db:
        row=db.get(AgentArtifactRecord,selected)
        owner=db.get(AgentRun,evidence["run_id"])
        provenance=json.loads(row.provenance_json)
        if damage=="internal":row.presentation_json=json.dumps({"visibility":"internal"})
        if damage=="producer_failed":db.get(AgentToolInvocation,provenance["tool_invocation_id"]).status="failed"
        if damage=="wrong_producer":
            provenance["tool_invocation_id"]="missing-invocation"
            row.provenance_json=json.dumps(provenance)
        if damage=="future":owner.session_sequence=db.get(AgentRun,admission.run_id).session_sequence+1
        if damage=="nonterminal":owner.status="running"
        db.commit()
        assert ArtifactRepository(db).available_artifact(session_id=evidence["session_id"],current_run_id=admission.run_id,artifact_id=selected) is None
        context=ContextAssembler(db).build(admission.run_id)
        assert selected not in [artifact.id for artifact in context.selected_artifacts]


@pytest.mark.parametrize("shape",["artifact_only", "artifact_and_document", "artifact_other_session"])
def test_actual_host_artifact_onask_shape_preserves_input_fence(produced,shape):
    runtime,evidence,scene=produced
    selected=evidence["artifacts"][2]["id"]
    # Preserve the captured pre-fix regression: the Host must not emit an
    # unnamespaced Object when the canonical artifact_id already identifies it.
    with pytest.raises(ValueError, match="object.kind"):
        ConversationInputReference.model_validate({"label":"Red producer",
            "object":{"kind":"artifact","id":selected,"version":1},"artifact_id":selected})
    artifact_ref=ConversationInputReference.model_validate({"label":"Red producer · v2",
        "artifact_id":selected})
    references=(artifact_ref,reference(scene)) if shape=="artifact_and_document" else (artifact_ref,)
    admission,_=admit(runtime,evidence,references,other_session=shape=="artifact_other_session")
    with runtime.factory() as db:
        current=db.get(AgentRun,admission.run_id)
        refs=resource_refs_for_run(db,current)
        assert len(refs)==(1 if shape=="artifact_and_document" else 0)
        available=ArtifactRepository(db).available_artifact(session_id=current.session_id,current_run_id=current.id,artifact_id=selected)
        assert (available is not None)==(shape=="artifact_and_document")
        selected_ids=[item.id for item in ContextAssembler(db).build(current.id).selected_artifacts]
        assert (selected in selected_ids)==(shape=="artifact_and_document")


@pytest.mark.parametrize("edge",["absent","derived_from","supports","cycle"])
def test_same_run_explicit_lineage_is_proven_but_not_implicit_authority(produced,edge):
    runtime,evidence,_=produced
    source,dependent=evidence["artifacts"][:2]
    with runtime.factory() as db:
        row=db.get(AgentArtifactRecord,dependent["id"])
        row.resource_refs_json=json.dumps(source["resource_refs"])
        row.relations_json=json.dumps([] if edge=="absent" else [{"relation":"derived_from" if edge=="cycle" else edge,
            "artifact_id":dependent["id"] if edge=="cycle" else source["id"]}])
        db.commit()
        result=ArtifactRepository(db).available_artifact(session_id=evidence["session_id"],current_run_id=evidence["run_id"],artifact_id=dependent["id"])
        assert (result is not None)==(edge=="derived_from")


@pytest.mark.parametrize("projection",["recent_contributor", "previous_outcome"])
@pytest.mark.parametrize("damage",["internal", "stale_fence", "producer_failed"])
def test_other_structured_context_artifacts_use_the_same_proof(produced,projection,damage):
    runtime,evidence,scene=produced
    selected=evidence["artifacts"][1 if damage=="stale_fence" else 2]["id"]
    admission,_=admit(runtime,evidence,reference(scene))
    captured=[]
    class Capture:
        def build(self,value:ContextContributionInput)->tuple[ContextFragment,...]:
            captured.extend(item.artifact_id for item in value.recent_artifacts)
            return ()
    with runtime.factory() as db:
        row=db.get(AgentArtifactRecord,selected)
        if damage=="internal":row.presentation_json=json.dumps({"visibility":"internal"})
        if damage=="producer_failed":db.get(AgentToolInvocation,json.loads(row.provenance_json)["tool_invocation_id"]).status="failed"
        if projection=="previous_outcome":
            # Keep an actual recovery outcome even when every Artifact has been
            # excluded, so its structured references remain under test.
            db.get(AgentRun,evidence["run_id"]).result_json=json.dumps({"completion_disposition":"bounded_partial"})
        db.commit()
        assert ArtifactRepository(db).available_artifact(session_id=evidence["session_id"],current_run_id=admission.run_id,artifact_id=selected) is None
        context=ContextAssembler(db,contributors=(lambda _:Capture(),)).build(admission.run_id)
        if projection=="recent_contributor":assert selected not in captured
        else:
            assert context.previous_run_outcome is not None
            assert selected not in [item.id for item in context.previous_run_outcome.artifacts]
            for outcome in context.previous_run_outcome.tool_outcomes:
                assert selected not in outcome.artifact_ids
                assert selected not in [item.id for item in outcome.artifacts]


@pytest.mark.parametrize("parameters",[{"url":"https://example.invalid/evil.glb"}, {"path":"../../outside.glb"}, {"version":99}])
def test_real_artifact_export_rejects_unsafe_external_parameters(produced,parameters):
    runtime,evidence,_=produced
    with runtime.factory() as db:
        artifact=ArtifactRepository(db).get(evidence["artifacts"][2]["id"])
    provider=runtime.snapshot.get_artifact_representation("dbfox.scene.revision","dbfox.scene.document.v1").provider
    with pytest.raises(Exception,match="Invalid Scene"):
        provider.execute(artifact,ArtifactRepresentationRequest(operation="export_glb",parameters=parameters),ArtifactRepresentationContext(artifact_loader=lambda _:None))


def test_worst_case_unicode_pages_remain_complete_and_model_bounded(tmp_path):
    with SceneRuntime(tmp_path/"unicode-red") as runtime:
        nodes=[{"id":f"unicode-{index}","kind":"light","name":"🦊"*120,"light_type":"spot",
            "position":[123.123456789,-234.234567891,345.345678912],"color":[0.123456789,0.234567891,0.345678912],
            "intensity":999999.123456789,"range":999999.123456789} for index in range(150)]
        steps=[Step(id="create",tool="scene_create",arguments={"title":"🦊"*160}),
            Step(id="lights",tool="object_create",arguments={"scene_id":"$scene_id","expected_version":"$version",
                "operation":{"kind":"object_create","objects":nodes}})]
        for index in range(8):
            steps.append(Step(id=f"page{index}",tool="scene_inspect",arguments={"scene_id":"$scene_id","version":"$version",
                "limit":100,"offset":0 if index==0 else f"$page{index-1}.next_offset"}))
        case=SceneCase(case_id="unicode-red",category="adversarial",prompt="Inspect every complete light record with bounded continuation pages.",steps=tuple(steps))
        evidence,_=_run_segment(runtime,case,repetition=1)
        assert evidence["run_status"]=="completed"
        pages=[item["facts"] for item in evidence["observations"] if item["call_id"].startswith("page")]
        returned=[node for page in pages for node in page["objects"]]
        assert len(returned)==len({node["id"] for node in returned})==150
        assert all(node["name"]=="🦊"*120 and node["range"]==999999.123456789 for node in returned)
        assert pages[0]["observation_truncated"] and pages[-1]["has_more"] is False
        assert all(page["returned"]==len(page["objects"]) for page in pages)
        assert evidence["max_observation_bytes"]<=25*1024
        for turn in evidence["scene_contexts"]:
            assert sum(len(fragment["content"]) for fragment in turn)<=4000
            assert all('"position"' not in fragment["content"] for fragment in turn)


@pytest.mark.parametrize("owner_status",["failed","cancelled","bounded_partial"])
def test_terminal_prior_plan_and_tool_references_filter_only_unavailable_artifacts(produced,owner_status):
    runtime,evidence,scene=produced
    stale=evidence["artifacts"][1]["id"]
    valid=evidence["artifacts"][2]["id"]
    with runtime.factory() as db:
        lease=SessionRepository(db).claim(session_id=evidence["session_id"],owner="scene-bench",ttl_seconds=600)
        turn=db.get(AgentArtifactRecord,valid).turn_id
        PlanRepository(db).update(lease=lease,run_id=evidence["run_id"],turn_id=turn,
            objective="Reuse the current export without replaying the old mutation.",
            steps=[PlanStep(id="done",title="Earlier successful work",status=PlanStepStatus.COMPLETED,
                artifact_ids=[stale,valid],note=f"Historical text mentions {stale}.")],summary="Prior durable plan")
        owner=db.get(AgentRun,evidence["run_id"])
        owner.status="completed" if owner_status=="bounded_partial" else owner_status
        if owner_status=="bounded_partial":owner.result_json=json.dumps({"completion_disposition":"bounded_partial","limitation_codes":["USER_BOUND"]})
        db.commit()
    admission,_=admit(runtime,evidence,reference(scene))
    with runtime.factory() as db:
        context=ContextAssembler(db).build(admission.run_id)
        previous=context.previous_run_outcome
        assert previous is not None and previous.plan is not None
        assert previous.plan.steps[0].artifact_ids==[valid]
        assert stale in previous.plan.steps[0].note  # Existing natural-language history is not authority.
        assert [item.id for item in previous.artifacts]==[valid]
        assert [artifact for item in previous.tool_outcomes for artifact in item.artifact_ids]==[valid]
        assert [artifact.id for item in previous.tool_outcomes for artifact in item.artifacts]==[valid]
