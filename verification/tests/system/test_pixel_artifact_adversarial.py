"""Independent attacks on real Pixel producers, input references and immutable views."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, ToolKey
from engine.agent.context import ContextAssembler
from engine.agent.references import ConversationInputReference
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.resource_refs import resource_refs_for_run
from engine.api.conversation_commands import _reference_resource_identities
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, AgentToolInvocation
from engine.runtime_composition import authorize_project_resources, build_product_run_loop
from verification.bench.capabilities.dbfox_pixel.runtime import PixelRuntime, PixelScript, run_segment
from verification.bench.capabilities.dbfox_pixel.schema import PixelCase, Step


@pytest.fixture
def produced(tmp_path):
    # No private store IDs are inserted into the scripted model. Subsequent IDs
    # and versions originate only in native function_call_output observations.
    with PixelRuntime(tmp_path / "producer") as runtime:
        case = PixelCase(case_id="adversarial-producer", category="adversarial", prompt="Create, inspect, paint one pixel and export.", steps=(
            Step(id="create", tool="pixel_create", arguments={"library_id": "$project", "title": "Red pixels", "width": 8, "height": 8, "expected_version": 0}),
            Step(id="frames", tool="pixel_inspect", arguments={"document_id": "$document_id", "kind": "frames"}),
            Step(id="layers", tool="pixel_inspect", arguments={"document_id": "$document_id", "kind": "layers"}),
            Step(id="paint", tool="pixel_rect", arguments={"document_id": "$document_id", "expected_version": "$revision", "operation": {
                "kind": "rect", "frame_id": "$frames.items.0.id", "layer_id": "$layers.items.0.id", "palette_index": 1,
                "rect": {"x": 0, "y": 0, "width": 1, "height": 1}}}),
            Step(id="export", tool="pixel_export", arguments={"document_id": "$document_id", "expected_version": "$revision"}),
        ))
        evidence, script = run_segment(runtime, case)
        assert evidence["run_status"] == "completed", evidence
        assert len(evidence["artifacts"]) == 3
        assert all(item["status"] == "succeeded" and item["attempts"] == 1 for item in evidence["invocations"])
        yield runtime, evidence, script.summary


def document_reference(summary):
    return ConversationInputReference.model_validate({"label": summary["title"],
        "authority": {"kind": "dbfox.pixel.document", "id": summary["document_id"]},
        "object": {"kind": "dbfox.pixel.frame", "id": "frame_1", "version": str(summary["revision"])},
        "locator": f"pixel://{summary['document_id']};revision={summary['revision']};frame=frame_1;layer=layer_1"})


def admit(runtime, evidence, references, *, other_session=False):
    session_id = evidence["session_id"]
    with runtime.factory() as db:
        if other_session:
            session_id = "other-" + uuid4().hex
            db.add(AgentSession(id=session_id, project_id=evidence["project_id"], title="Other chat"))
            db.commit()
        refs = authorize_project_resources(db, evidence["project_id"], _reference_resource_identities(references), snapshot=runtime.snapshot)
        sessions = SessionRepository(db)
        admission = sessions.admit(session_id=session_id, resource_refs=refs, references=references,
            content="Inspect the attached Pixel reference.", idempotency_key=uuid4().hex,
            llm_credential_id="pixel-red-scripted", api_base=None, model_name="scripted", request_payload={"purpose": "Pixel red team"})
        # The fixture coordinator retains its live lease after the producer Run.
        # Continue as that coordinator; a different owner correctly cannot steal it.
        lease = sessions.claim(session_id=session_id, owner="pixel-bench", ttl_seconds=600)
        assert lease is not None
        sessions.promote_next_input(lease=lease)
        db.commit()
    return admission


def test_producer_invocation_proves_prewrite_refs_and_current_export(produced):
    runtime, evidence, summary = produced
    created, painted, exported = evidence["artifacts"]
    assert created["payload"]["revision"] == 1 and created["resource_refs"][0]["kind"] == "dbfox.pixel.library"
    assert painted["payload"]["revision"] == 2 and str(painted["resource_refs"][0]["version"]) == "1"
    assert exported["payload"]["revision"] == 2 and str(exported["resource_refs"][0]["version"]) == "2"
    with runtime.factory() as db:
        repo = ArtifactRepository(db)
        assert all(repo.available_artifact(session_id=evidence["session_id"], current_run_id=evidence["run_id"], artifact_id=item["id"]) for item in evidence["artifacts"])
    admission = admit(runtime, evidence, (document_reference(summary),))
    with runtime.factory() as db:
        repo = ArtifactRepository(db)
        assert [repo.available_artifact(session_id=evidence["session_id"], current_run_id=admission.run_id,
            artifact_id=item["id"]) is not None for item in evidence["artifacts"]] == [False, False, True]


@pytest.mark.parametrize("shape", ["document", "artifact_only", "artifact_and_document", "mutation_and_document", "other_chat"])
def test_public_onask_shapes_do_not_implicitly_upgrade_artifact_authority(produced, shape):
    runtime, evidence, summary = produced
    selected = evidence["artifacts"][1 if shape == "mutation_and_document" else 2]["id"]
    artifact_ref = ConversationInputReference(label="Pixel snapshot", artifact_id=selected)
    refs = (document_reference(summary),) if shape == "document" else (artifact_ref,)
    if shape in ("artifact_and_document", "mutation_and_document", "other_chat"):
        refs += (document_reference(summary),)
    admission = admit(runtime, evidence, refs, other_session=shape == "other_chat")
    with runtime.factory() as db:
        run = db.get(AgentRun, admission.run_id)
        actual = resource_refs_for_run(db, run)
        assert len(actual) == (0 if shape == "artifact_only" else 1)
        if actual:
            assert str(actual[0].version) == "2" and actual[0].id == summary["document_id"]
        available = ArtifactRepository(db).available_artifact(session_id=run.session_id, current_run_id=run.id, artifact_id=selected)
        assert (available is not None) == (shape in ("document", "artifact_and_document"))
        selected_ids = [item.id for item in ContextAssembler(db).build(run.id).selected_artifacts]
        assert (selected in selected_ids) == (shape == "artifact_and_document")


@pytest.mark.parametrize("damage", ["producer_failed", "missing_producer", "wrong_existing_producer", "future", "nonterminal", "internal"])
def test_selected_recent_and_recovery_contexts_cannot_bypass_producer_proof(produced, damage):
    runtime, evidence, summary = produced
    selected = evidence["artifacts"][2]["id"]
    admission = admit(runtime, evidence, (document_reference(summary), ConversationInputReference(label="Snapshot", artifact_id=selected)))
    seen = []
    class Capture:
        def build(self, value):
            seen.extend(item.artifact_id for item in value.recent_artifacts)
            return ()
    with runtime.factory() as db:
        row = db.get(AgentArtifactRecord, selected)
        producer_run = db.get(AgentRun, evidence["run_id"])
        producer_run.result_json = json.dumps({"completion_disposition": "bounded_partial"})
        provenance = json.loads(row.provenance_json)
        if damage == "producer_failed":
            db.get(AgentToolInvocation, provenance["tool_invocation_id"]).status = "failed"
        if damage in ("missing_producer", "wrong_existing_producer"):
            provenance["tool_invocation_id"] = "missing" if damage == "missing_producer" else evidence["invocations"][0]["id"]
            row.provenance_json = json.dumps(provenance)
        if damage == "future":
            producer_run.session_sequence = db.get(AgentRun, admission.run_id).session_sequence + 1
        if damage == "nonterminal":
            producer_run.status = "running"
        if damage == "internal":
            row.presentation_json = json.dumps({"visibility": "internal"})
        db.commit()
        assert ArtifactRepository(db).available_artifact(session_id=evidence["session_id"], current_run_id=admission.run_id, artifact_id=selected) is None
        context = ContextAssembler(db, contributors=(lambda _: Capture(),)).build(admission.run_id)
        assert selected not in seen
        assert selected not in [item.id for item in context.selected_artifacts]
        if context.previous_run_outcome:
            assert selected not in [item.id for item in context.previous_run_outcome.artifacts]
            for outcome in context.previous_run_outcome.tool_outcomes:
                assert selected not in outcome.artifact_ids


@pytest.mark.parametrize("edge", ["none", "derived_from", "supports", "cycle"])
def test_same_run_dependency_requires_exact_explicit_lineage(produced, edge):
    runtime, evidence, _ = produced
    source, dependent = evidence["artifacts"][:2]
    with runtime.factory() as db:
        row = db.get(AgentArtifactRecord, dependent["id"])
        row.resource_refs_json = json.dumps(source["resource_refs"])
        row.relations_json = json.dumps([] if edge == "none" else [{"relation": "derived_from" if edge == "cycle" else edge,
            "artifact_id": dependent["id"] if edge == "cycle" else source["id"]}])
        db.commit()
        result = ArtifactRepository(db).available_artifact(session_id=evidence["session_id"], current_run_id=evidence["run_id"], artifact_id=dependent["id"])
        assert (result is not None) == (edge == "derived_from")


@pytest.mark.parametrize("parameters", [{"url": "https://example.invalid/a.png"}, {"path": "../../a.png"}, {"revision": 999}, {"document_id": "other"}])
def test_representation_rejects_external_or_identity_override_parameters(produced, parameters):
    runtime, evidence, _ = produced
    with runtime.factory() as db:
        artifact = ArtifactRepository(db).get(evidence["artifacts"][2]["id"])
    provider = runtime.snapshot.get_artifact_representation("dbfox.pixel.revision", "dbfox.pixel.sprite.v1").provider
    with pytest.raises(Exception, match="parameters are invalid"):
        provider.execute(artifact, ArtifactRepresentationRequest(operation="sheet", parameters=parameters),
            ArtifactRepresentationContext(artifact_loader=lambda _: None))


def test_document_onask_continuation_executes_via_actual_product_factory(produced):
    runtime, evidence, summary = produced
    admission = admit(runtime, evidence, (document_reference(summary),))
    case = PixelCase(case_id="native-factory-consumer", category="adversarial", prompt="Inspect and edit the selected frame.", steps=(
        Step(id="frames", tool="pixel_inspect", arguments={"document_id": summary["document_id"], "kind": "frames"}),
        Step(id="layers", tool="pixel_inspect", arguments={"document_id": "$document_id", "kind": "layers"}),
        Step(id="local", tool="pixel_rect", arguments={"document_id": "$document_id", "expected_version": "$revision", "operation": {
            "kind": "rect", "frame_id": "$frames.items.0.id", "layer_id": "$layers.items.0.id", "palette_index": 1,
            "rect": {"x": 1, "y": 1, "width": 1, "height": 1}}}),
    ))
    script = PixelScript(case, evidence["project_id"], lambda _: None, {item.tool.name: runtime.registry.provider_name_for_key(
        ToolKey(owner_id="dbfox.pixel", local_name=item.tool.name)) for item in runtime.snapshot.tools if item.owner_id == "dbfox.pixel"})
    with runtime.factory() as db:
        lease = SessionRepository(db).claim(session_id=evidence["session_id"], owner="pixel-bench", ttl_seconds=600)
        assert lease is not None
        db.commit()
    # Exercise the production composition function; only the external model
    # boundary is controlled. No resolver or dispatcher is injected by this test.
    loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
    loop.model_factory = lambda _: script
    try:
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
    assert script.observations["frames"]["facts"]["summary"]["revision"] == 2
    assert script.observations["local"]["facts"]["revision"] == 3
    assert script.observations["local"]["facts"]["changed_pixel_count"] == 1
    with runtime.factory() as db:
        assert db.get(AgentRun, admission.run_id).status == "completed"
        calls = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        assert len(calls) == 3 and all(item.status == "succeeded" and item.attempt_count == 1 for item in calls)
        assert all(item.package_digest == runtime.package.package_digest for item in calls)
