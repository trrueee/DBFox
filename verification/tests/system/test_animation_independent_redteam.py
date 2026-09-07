"""Independent installed Animation attacks, using production admission/Dispatcher.

Model HTTP alone is scripted. Human writes use registered operations. No private
Scene/Animation import, synthetic resource resolution, or invocation-scope edits.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import httpx
from openai import AsyncOpenAI
import pytest
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest, DlcOperationContext, DlcOperationError, RequestedResourceRef
from engine.agent.context_budget import estimate_input_items_tokens, estimate_tool_schema_tokens
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import active_runtime_snapshot, authorize_project_resources, build_product_run_loop, build_product_tool_registry, initialize_runtime_snapshot, set_active_runtime_snapshot
from verification.support.metadata import create_migrated_metadata_engine
from verification.tests.system.test_scene_animation_composition import ModelBoundary


class Boundary(ModelBoundary):
    def __init__(self, registry, plan):
        self.supplied_plan = plan
        super().__init__(registry)

    def steps(self):
        for owner, name, data, status in self.supplied_plan(self):
            self.expected_status = status
            yield owner, name, data


class Installed:
    def __init__(self, root):
        self.previous = active_runtime_snapshot()
        self.service = DlcPackageService(root / "dlcs")
        self.digests = {}
        for owner in ("dbfox.scene", "dbfox.animation"):
            built = build_dlc_package_from_source(Path(__file__).resolve().parents[3] / "dlcs" / owner,
                private_key=Ed25519PrivateKey.generate())
            path = root / (owner + ".dbfox-dlc")
            path.write_bytes(built.archive_bytes)
            self.service.trust_publisher_from_file(path, expected_package_digest=built.package_digest,
                expected_publisher_key_id=built.publisher_fingerprint)
            self.service.install_from_file(path)
            self.service.set_desired_enabled(owner, True)
            self.digests[owner] = built.package_digest
        self.reload()
        self.engine = create_migrated_metadata_engine(root / "metadata.sqlite")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def reload(self):
        self.snapshot = initialize_runtime_snapshot(storage_root=self.service.storage_root)
        assert not self.snapshot.activation_failures

    def close(self):
        set_active_runtime_snapshot(self.previous)
        self.engine.dispose()

    def op(self, name, data, project="review"):
        spec = self.snapshot.get_operation("dbfox.animation", name).spec
        return spec.handler(spec.input_model.model_validate(data), DlcOperationContext(
            dlc_id="dbfox.animation", operation_name=name, project_id=project))

    def create(self, project="review"):
        return self.op("animations.create", {"title": "Independent motion", "request_id": uuid4().hex}, project).animation

    def apply(self, summary, operation, request_id=None):
        return self.op("animations.apply", {"animation_id": summary.id, "expected_version": summary.version,
            "operation": operation, "request_id": request_id or uuid4().hex}, summary.project_id).animation

    def seed(self):
        summary = self.create()
        for operation in (
            {"kind": "target_create", "target": {"id": "fox", "name": "Fox"}},
            {"kind": "track_create", "track": {"id": "motion", "name": "Move X", "target_id": "fox", "property": "position.x"}},
            {"kind": "keyframe_add", "keyframes": [{"id": "start", "track_id": "motion", "tick": 0, "value": 0}, {"id": "end", "track_id": "motion", "tick": 4000, "value": 4}]},
        ):
            summary = self.apply(summary, operation)
        return summary

    def counts(self):
        paths = list(self.service.storage_root.rglob("animation.sqlite3"))
        assert len(paths) == 1
        with sqlite3.connect(paths[0]) as db:
            return {name: db.execute("SELECT count(*) FROM " + name).fetchone()[0]
                for name in ("documents", "revisions", "receipts", "entity_ids")}

    def run(self, plan, refs, project="review"):
        session_id = uuid4().hex
        with self.factory() as db:
            if db.get(Project, project) is None:
                db.add(Project(id=project, name="Independent Animation " + project)); db.flush()
            db.add(AgentSession(id=session_id, project_id=project, title="Boundary review")); db.commit()
            scopes = authorize_project_resources(db, project, tuple(refs), snapshot=self.snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id=session_id, resource_refs=scopes,
                content="Inspect the authorized animation; perform only the specified valid edit. Explain rejected edits without claiming success.",
                idempotency_key=uuid4().hex, llm_credential_id="scripted", api_base=None, model_name="gpt-5.4", request_payload={})
            lease = sessions.claim(session_id=session_id, owner="independent-review", ttl_seconds=300)
            assert lease is not None
            sessions.promote_next_input(lease=lease); db.commit()
        self.run_id = admission.run_id
        boundary = Boundary(build_product_tool_registry(self.snapshot), plan)
        loop = build_product_run_loop(session_factory=self.factory, snapshot=self.snapshot)
        def adapter(settings):
            return OpenAIModelAdapter(client=AsyncOpenAI(api_key="mock-transport-only", base_url="https://scene-animation-model.invalid/v1",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(boundary.respond)), max_retries=0), model_name=settings.model_name, owns_client=True)
        loop.model_factory = adapter
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
            assert not boundary.errors, boundary.errors
            assert max(estimate_input_items_tokens(r["input"]) + estimate_tool_schema_tokens(r["tools"])
                for r in boundary.requests) <= loop.definition.limits.max_prompt_tokens == 32768
            with self.factory() as db:
                run = db.get(AgentRun, admission.run_id)
                status = run.status
                artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
                invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
                assert all(i.package_digest == self.digests[i.owner_id] for i in invocations)
            return boundary, artifacts, invocations, status
        finally:
            loop.close()

    def export(self, artifact):
        provider = self.snapshot.get_artifact_representation(artifact.type, "dbfox.animation.document.v1").provider
        return b"".join(provider.execute(artifact, ArtifactRepresentationRequest(operation="export_json", parameters={}),
            ArtifactRepresentationContext(artifact_loader=lambda identity: None)).chunks)


@pytest.fixture
def installed(tmp_path):
    runtime = Installed(tmp_path)
    try:
        yield runtime
    finally:
        runtime.close()


def document(summary):
    return RequestedResourceRef(kind="dbfox.animation.document", id=summary.id)


def rename(summary, expected=None):
    return {"animation_id": summary.id, "expected_version": expected or summary.version,
        "operation": {"kind": "animation_rename", "title": "Unauthorized overwrite"}}


def test_exact_project_selector_and_cross_project_rejection(installed):
    allowed, selected, foreign = installed.create(), installed.create(), installed.create("foreign")
    before = installed.counts()
    def select(model):
        yield "dbfox.animation", "animation_rename", rename(selected), "succeeded"
    _, _, invocations, _ = installed.run(select, [document(allowed)])
    assert len(invocations) == 1
    scopes = json.loads(invocations[0].resource_refs_json)
    assert len(scopes) == 1 and scopes[0]["id"] == selected.id and scopes[0]["version"] == 1
    before = installed.counts()
    def reject(model):
        yield "dbfox.animation", "animation_rename", rename(foreign), "rejected"
    _, artifacts, invocations, _ = installed.run(reject, [document(allowed)])
    assert not artifacts and len(invocations) == 1 and invocations[0].status == "rejected"
    with pytest.raises(DlcOperationError, match="unavailable in this Project"):
        installed.op("animations.get", {"animation_id": foreign.id, "section": "targets"})
    with pytest.raises(DlcOperationError, match="unavailable in this Project"):
        installed.op("animations.apply", {**rename(foreign), "request_id": uuid4().hex})
    assert installed.counts() == before


def test_human_cas_write_during_model_request_rejects_stale_model_and_future_inspection(installed):
    initial = installed.seed()
    before = installed.counts()
    def plan(model):
        # Represents a real concurrent Workbench edit after the model request was assembled.
        current = installed.apply(initial, {"kind": "marker_set", "marker": {"id": "human", "name": "Human", "tick": 10}})
        yield "dbfox.animation", "animation_rename", rename(initial), "failed"
        yield "dbfox.animation", "animation_inspect", {"animation_id": initial.id, "version": current.version + 1}, "failed"
    _, artifacts, invocations, _ = installed.run(plan, [document(initial)])
    assert not artifacts and len(invocations) == 2 and all(i.status == "failed" for i in invocations)
    current = installed.op("animations.get", {"animation_id": initial.id, "section": "markers"})
    assert current.animation.version == initial.version + 1 and current.items[0].id == "human"
    assert installed.counts()["revisions"] == before["revisions"] + 1
    assert installed.counts()["receipts"] == before["receipts"] + 1


def test_cancel_during_model_http_prevents_owner_write(installed):
    initial = installed.seed()
    before = installed.counts()
    def plan(model):
        with installed.factory() as db:
            RunRepository(db).request_cancel(run_id=installed.run_id)
            db.commit()
        yield "dbfox.animation", "animation_rename", rename(initial), "failed"
    _, artifacts, _, status = installed.run(plan, [document(initial)])
    assert status == "cancelled" and not artifacts
    assert installed.counts() == before


@pytest.mark.parametrize("operation", [
    {"kind": "keyframe_add", "keyframes": [{"id": "new", "track_id": "motion", "tick": 3000, "value": 7}, {"id": "bad", "track_id": "foreign", "tick": 3500, "value": 9}]},
    {"kind": "keyframe_move", "keyframes": [{"id": "end", "tick": 0, "value": 4}]},
    {"kind": "target_create", "target": {"id": "fake", "name": "Forged source", "source": {"artifact_id": "fake", "scene_id": "fake", "version": 1, "content_hash": "0" * 64, "object_id": "fox"}}},
])
def test_invalid_batch_collision_and_forged_source_do_not_leave_receipts(installed, operation):
    initial = installed.seed()
    before = installed.counts()
    def plan(model):
        yield "dbfox.animation", operation["kind"], {"animation_id": initial.id, "expected_version": initial.version, "operation": operation}, "rejected" if operation["kind"] == "target_create" else "failed"
    _, artifacts, _, _ = installed.run(plan, [document(initial)])
    assert not artifacts and installed.counts() == before


def test_public_cas_race_and_receipt_identity_are_durable(installed):
    initial = installed.seed()
    before = installed.counts()
    barrier = threading.Barrier(2)
    def write(name):
        barrier.wait(timeout=3)
        operation = {"kind": "animation_rename", "title": name}
        try:
            return installed.apply(initial, operation, name), operation, name
        except DlcOperationError as error:
            assert error.code == "ANIMATION_STALE"
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [r for r in pool.map(write, ["human-a", "human-b"]) if r]
    assert len(winners) == 1
    result, operation, request = winners[0]
    installed.reload()
    assert installed.apply(initial, operation, request) == result
    with pytest.raises(DlcOperationError, match="already used"):
        installed.apply(result, {"kind": "animation_rename", "title": "Different request"}, request)
    assert installed.counts()["revisions"] == before["revisions"] + 1
    assert installed.counts()["receipts"] == before["receipts"] + 1


def test_deleted_document_restart_and_tampered_artifact_preserve_fixed_track_bytes(installed):
    initial = installed.seed()
    def plan(model):
        yield "dbfox.animation", "animation_export", {"animation_id": initial.id, "expected_version": initial.version}, "succeeded"
    _, artifacts, _, _ = installed.run(plan, [document(initial)])
    artifact = next(a for a in artifacts if a.type == "dbfox.animation.revision")
    fixed = installed.export(artifact)
    assert hashlib.sha256(fixed).hexdigest() == artifact.payload["content_hash"]
    changed = installed.apply(initial, {"kind": "keyframe_move", "keyframes": [{"id": "end", "tick": 4001, "value": 5}]})
    installed.op("animations.delete", {"animation_id": initial.id, "expected_version": changed.version, "request_id": uuid4().hex})
    installed.service.set_desired_enabled("dbfox.animation", False)
    installed.reload()
    assert not any(t.owner_id == "dbfox.animation" for t in installed.snapshot.tools)
    installed.service.set_desired_enabled("dbfox.animation", True)
    installed.reload()
    assert installed.export(artifact) == fixed
    assert next(k for k in json.loads(fixed)["keyframes"] if k["id"] == "end")["tick"] == 4000
    for patch in ({"content_hash": "0" * 64}, {"project_id": "foreign"}, {"version": 9999}):
        forged = artifact.model_copy(update={"payload": {**artifact.payload, **patch}})
        with pytest.raises(ArtifactRepresentationError):
            installed.export(forged)


@pytest.mark.parametrize("source_project", ["review", "foreign"])
def test_scene_artifact_outside_current_session_cannot_be_bound(installed, source_project):
    def create_scene(model):
        yield "dbfox.scene", "scene_create", {"title": "Separate session source"}, "succeeded"
        scene = model.outputs[-1]["facts"]["scene"]
        yield "dbfox.scene", "object_create", {"scene_id": scene["id"], "expected_version": 1,
            "operation": {"kind": "object_create", "objects": [{"kind": "group", "id": "fox", "name": "Fox"}]}}, "succeeded"
    _, sources, _, _ = installed.run(create_scene,
        [RequestedResourceRef(kind="dbfox.scene.library", id=source_project)], project=source_project)
    source = next(a for a in sources if a.type == "dbfox.scene.revision" and a.payload["version"] == 2)
    animation = installed.create()
    before = installed.counts()
    def bind(model):
        yield "dbfox.animation", "scene_bind", {"animation_id": animation.id, "expected_version": 1,
            "artifact_id": source.id, "object_ids": ["fox"]}, "failed"
    _, artifacts, invocations, _ = installed.run(bind, [document(animation)])
    assert not artifacts and len(invocations) == 1 and invocations[0].status == "failed"
    assert installed.counts() == before
